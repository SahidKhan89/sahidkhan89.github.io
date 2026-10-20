import { readFileSync, writeFileSync, existsSync } from 'fs';
import Anthropic from '@anthropic-ai/sdk';

// Finds a public Threads post about stocks/markets and replies to it, to get
// Stock Score in front of other accounts' audiences. One reply per run — the
// schedule (cron-job.org) controls daily volume, kept low on purpose: bulk
// automated replies are what Threads' spam detection looks for.

// ─── Retry helper ────────────────────────────────────────────────────────────

async function withRetry(label, fn, attempts = 3, delayMs = 4000) {
  for (let i = 1; i <= attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === attempts) throw err;
      console.warn(`  [${label}] attempt ${i} failed: ${err.message} — retrying in ${delayMs / 1000}s…`);
      await new Promise(r => setTimeout(r, delayMs));
    }
  }
}

// ─── Config ──────────────────────────────────────────────────────────────────

const TRACKING       = new URL('../data/replied_threads.json', import.meta.url).pathname;
const MAX_HISTORY    = 1000;
const MAX_AGE_HOURS  = 12;   // only reply while the conversation is still live
const AUTHOR_COOLDOWN_DAYS = 7; // never reply to the same person more than once a week
const MAX_CANDIDATES = 12;   // posts shown to the model per run
const MIN_TEXT_LEN   = 40;   // skip one-liners — nothing to engage with
const REPLY_LIMIT    = 280;

// Two keywords per run, rotated by hour so consecutive runs search different
// topics. Broad terms surface conversation; tickers surface the big names.
const KEYWORDS = [
  'stock market', 'S&P 500', 'Nasdaq', 'earnings', 'Fed rate', 'inflation',
  'dividend stocks', 'investing', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN',
  'META', 'GOOGL', 'recession', 'ETF', 'bull market', 'stocks to buy',
];

// Promo/spam patterns — replying under these makes the account look like
// part of the same scene.
const SPAM_RE = /\b(giveaway|dm me|telegram|whatsapp|signals? group|join my|link in bio|airdrop|100x|guaranteed|free money|onlyfans|promo code)\b/i;

const GRAPH = 'https://graph.threads.net/v1.0';

// ─── Threads ──────────────────────────────────────────────────────────────────

async function threadsGet(path, params) {
  const qs = new URLSearchParams({ ...params, access_token: process.env.THREADS_ACCESS_TOKEN });
  const resp = await fetch(`${GRAPH}/${path}?${qs}`, { signal: AbortSignal.timeout(15000) });
  const data = await resp.json();
  if (data.error) throw new Error(`Threads ${path} error: ${data.error.message}`);
  return data;
}

async function searchPosts(keyword) {
  const since = Math.floor((Date.now() - MAX_AGE_HOURS * 3_600_000) / 1000);
  const { data = [] } = await threadsGet('keyword_search', {
    q: keyword,
    search_type: 'TOP',
    media_type: 'TEXT',
    since: String(since),
    limit: '25',
    fields: 'id,text,permalink,timestamp,username,is_reply,is_quote_post',
  });
  return data;
}

async function postReply(replyToId, text) {
  const token  = process.env.THREADS_ACCESS_TOKEN;
  const base   = `${GRAPH}/${process.env.THREADS_USER_ID}`;

  const createResp = await fetch(`${base}/threads`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ media_type: 'TEXT', text, reply_to_id: replyToId, access_token: token }),
  });
  const { id, error } = await createResp.json();
  if (error) throw new Error(`Threads create error: ${error.message}`);

  await new Promise(r => setTimeout(r, 5000));

  const pubResp = await fetch(`${base}/threads_publish`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ creation_id: id, access_token: token }),
  });
  const pubData = await pubResp.json();
  if (pubData.error) throw new Error(`Threads publish error: ${pubData.error.message}`);
  return pubData.id;
}

// ─── LLM pick + draft ──────────────────────────────────────────────────────────

const anthropic = new Anthropic();

const SYSTEM = [
  "You reply to other people's Threads posts on behalf of Stock Score, a stock market app for everyday retail investors.",
  "The goal is for readers of the post to find the reply genuinely useful and tap through to the profile — not to advertise.",
  "You'll get a numbered list of recent public posts about stocks and markets. Pick the ONE where a thoughtful reply adds the most, or none if no post is worth replying to.",
  "Skip posts that are: promotional or spammy, rage-bait, personal (someone's losses, health, politics), crypto pumping, asking for DMs, or that you couldn't add anything factual to. Picking none is a perfectly good outcome — a bad reply is worse than no reply.",
  "The reply must add something specific: a relevant fact, a bit of context, a fair counterpoint, or a sharp question. Respond to what the post actually says.",
  "Sound like a knowledgeable person, not a brand: casual, short, contractions fine. One or two sentences.",
  'Never: link, mention Stock Score or "our app", use hashtags, open with praise ("Great post!", "So true"), tell anyone to buy or sell, or make price predictions.',
  "Only state facts you're confident were true as of the post's date — if unsure of a number, make the point without it.",
  `Keep the reply under ${REPLY_LIMIT} characters. No emoji unless it really fits, and at most one.`,
].join(' ');

const OUTPUT_SCHEMA = {
  type: 'object',
  properties: {
    choice: { type: 'integer', description: 'Number of the chosen post, or 0 for none.' },
    reply:  { type: 'string',  description: 'The reply text. Empty when choice is 0.' },
  },
  required: ['choice', 'reply'],
  additionalProperties: false,
};

async function pickAndDraft(candidates) {
  const list = candidates
    .map((p, i) => `${i + 1}. @${p.username} (${p.timestamp}):\n${p.text}`)
    .join('\n\n');

  const response = await anthropic.beta.messages.create({
    model: 'claude-sonnet-5-5',
    max_tokens: 4000,
    output_config: { effort: 'low', format: { type: 'json_schema', schema: OUTPUT_SCHEMA } },
    // On a safety decline, re-run on Anthropic's recommended fallback model
    // instead of losing the run.
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
    system: SYSTEM,
    messages: [{ role: 'user', content: `Today is ${new Date().toISOString().slice(0, 10)}.\n\nPosts:\n\n${list}` }],
  });

  const { input_tokens, output_tokens } = response.usage;
  console.log(`  tokens: ${input_tokens} in / ${output_tokens} out`);

  if (response.stop_reason === 'refusal') return { choice: 0 };
  const text = response.content.find(b => b.type === 'text')?.text;
  if (!text) throw new Error('No text in LLM response');
  const { choice, reply } = JSON.parse(text);
  if (!choice) return { choice: 0 };
  if (choice < 1 || choice > candidates.length) throw new Error(`LLM picked out-of-range post ${choice}`);
  if (!reply?.trim()) throw new Error('LLM picked a post but wrote no reply');
  return { post: candidates[choice - 1], reply: reply.trim().slice(0, REPLY_LIMIT) };
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function loadTracking() {
  if (!existsSync(TRACKING)) return { replied: [] };
  return JSON.parse(readFileSync(TRACKING, 'utf8'));
}

async function main() {
  if (!process.env.THREADS_ACCESS_TOKEN || !process.env.THREADS_USER_ID) {
    throw new Error('THREADS_ACCESS_TOKEN and THREADS_USER_ID are required (search needs them too).');
  }
  const isDryRun = process.env.REPLY_DRY_RUN === 'true';

  const tracking = loadTracking();
  const repliedIds = new Set(tracking.replied.map(r => r.id));
  const cooldownCutoff = Date.now() - AUTHOR_COOLDOWN_DAYS * 86_400_000;
  const recentAuthors = new Set(
    tracking.replied.filter(r => new Date(r.at).getTime() > cooldownCutoff).map(r => r.username),
  );

  const { username: me } = await threadsGet('me', { fields: 'username' });

  const hour = new Date().getUTCHours();
  const keywords = [KEYWORDS[hour % KEYWORDS.length], KEYWORDS[(hour * 7 + 3) % KEYWORDS.length]];

  const seen = new Set();
  const candidates = [];
  for (const kw of [...new Set(keywords)]) {
    const posts = await withRetry(`search "${kw}"`, () => searchPosts(kw));
    console.log(`Search "${kw}": ${posts.length} posts`);
    for (const p of posts) {
      if (seen.has(p.id)) continue;
      seen.add(p.id);
      if (p.username === me || p.is_reply || repliedIds.has(p.id) || recentAuthors.has(p.username)) continue;
      if (!p.text || p.text.length < MIN_TEXT_LEN || SPAM_RE.test(p.text)) continue;
      candidates.push(p);
    }
  }

  // Without the threads_keyword_search permission approved, search only
  // returns your own posts — which all get filtered out above.
  if (candidates.length === 0) {
    console.log('No candidate posts this run. (If every run says this, check the app has threads_keyword_search approved — without it, search only returns your own posts.)');
    return;
  }

  const shortlist = candidates.slice(0, MAX_CANDIDATES);
  console.log(`\nAsking model to pick from ${shortlist.length} candidates…`);
  const result = await withRetry('LLM', () => pickAndDraft(shortlist));

  if (!result.post) {
    console.log('Model skipped — nothing worth replying to this run.');
    return;
  }

  console.log('\n--- Replying to ---');
  console.log(`@${result.post.username}: ${result.post.text}`);
  console.log(result.post.permalink);
  console.log('\n--- Reply ---');
  console.log(result.reply);

  if (isDryRun) {
    console.log('\nREPLY_DRY_RUN=true — not posting.');
    return;
  }

  try {
    const id = await withRetry('Threads', () => postReply(result.post.id, result.reply));
    console.log(`\n  ✓ Replied: ${id}`);
    tracking.replied.push({
      id: result.post.id,
      username: result.post.username,
      reply_id: id,
      at: new Date().toISOString(),
    });
    tracking.replied = tracking.replied.slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    console.log('Tracking file updated.');
  } catch (err) {
    console.error(`  ✗ Threads: ${err.message}`);
    process.exit(1);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
