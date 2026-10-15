import { readFileSync, writeFileSync } from 'fs';
import Anthropic from '@anthropic-ai/sdk';

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

const CNBC_RSS_URL = process.env.CNBC_RSS_URL
  || 'https://www.cnbc.com/id/100003114/device/rss/rss.html'; // US Top News and Analysis — broad market/business hot topics, not earnings-only
const TRACKING    = new URL('../data/posted_cnbc_threads.json', import.meta.url).pathname;
const MAX_HISTORY = 500;
const CAPTION_LIMIT = 500; // Threads character limit
const MAX_AGE_HOURS = 72;  // don't post news older than this
const MAX_AGE_MS = MAX_AGE_HOURS * 60 * 60 * 1000;
const MAX_RELEVANCE_CHECKS = 5; // LLM calls per run before giving up on finding a market story

// ─── RSS parsing ───────────────────────────────────────────────────────────────

function decodeXmlEntities(str) {
  return str
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .trim();
}

function extractTag(block, tag) {
  const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i');
  const match = re.exec(block);
  if (!match) return null;
  const content = match[1].trim();
  const cdataMatch = /^<!\[CDATA\[([\s\S]*)\]\]>$/.exec(content);
  return decodeXmlEntities(cdataMatch ? cdataMatch[1] : content);
}

function parsePubDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return Number.isNaN(d.getTime()) ? null : d;
}

function parseRssItems(xml) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let match;
  while ((match = itemRegex.exec(xml))) {
    const block = match[1];
    const title = extractTag(block, 'title');
    const link  = extractTag(block, 'link');
    if (!title || !link) continue;
    items.push({
      title,
      link,
      description: extractTag(block, 'description') || '',
      pubDate:     extractTag(block, 'pubDate'),
    });
  }
  return items;
}

// ─── Hashtag generation ───────────────────────────────────────────────────────

const COMPANIES = [
  ['Apple', 'AAPL'], ['Microsoft', 'MSFT'], ['Google', 'GOOGL'], ['Alphabet', 'GOOGL'],
  ['Amazon', 'AMZN'], ['Meta', 'META'], ['Tesla', 'TSLA'], ['Nvidia', 'NVDA'],
  ['Netflix', 'NFLX'], ['Oracle', 'ORCL'], ['Salesforce', 'CRM'], ['Intel', 'INTC'],
  ['AMD', 'AMD'], ['Qualcomm', 'QCOM'], ['Broadcom', 'AVGO'], ['Adobe', 'ADBE'],
  ['Palantir', 'PLTR'], ['Uber', 'UBER'], ['Airbnb', 'ABNB'], ['Spotify', 'SPOT'],
  ['JPMorgan', 'JPM'], ['Goldman Sachs', 'GS'], ['Goldman', 'GS'],
  ['Morgan Stanley', 'MS'], ['Bank of America', 'BAC'], ['Wells Fargo', 'WFC'],
  ['Citigroup', 'C'], ['Citi', 'C'], ['BlackRock', 'BLK'], ['Berkshire', 'BRK.B'],
  ['Visa', 'V'], ['Mastercard', 'MA'], ['PayPal', 'PYPL'],
  ['ExxonMobil', 'XOM'], ['Exxon', 'XOM'], ['Chevron', 'CVX'], ['Shell', 'SHEL'], ['BP', 'BP'],
  ['Pfizer', 'PFE'], ['Moderna', 'MRNA'], ['Eli Lilly', 'LLY'],
  ['Johnson & Johnson', 'JNJ'], ['UnitedHealth', 'UNH'], ['AstraZeneca', 'AZN'],
  ['Walmart', 'WMT'], ['Target', 'TGT'], ['Nike', 'NKE'], ['Costco', 'COST'],
  ["McDonald's", 'MCD'], ['Starbucks', 'SBUX'],
  ['Ford', 'F'], ['General Motors', 'GM'], ['Toyota', 'TM'],
  ['Delta', 'DAL'], ['United Airlines', 'UAL'], ['American Airlines', 'AAL'],
  ['HSBC', 'HSBA'], ['Barclays', 'BARC'], ['Lloyds', 'LLOY'],
  ['Rolls-Royce', 'RR'], ['Vodafone', 'VOD'], ['GSK', 'GSK'],
  ['Honeywell', 'HON'], ['Dover', 'DOV'], ['Albertsons', 'ACI'],
];

// Topic tags, used when the story isn't mainly about one listed company. The
// descriptions are shown to the model so it knows what each tag covers.
const TOPICS = [
  ['Earnings',    'company quarterly results, revenue/profit figures, guidance'],
  ['Economy',     'GDP, jobs, unemployment, recession, consumer spending'],
  ['Fed',         'Federal Reserve, interest-rate decisions, central bank policy'],
  ['Inflation',   'CPI/PCE, prices, tariffs and their effect on costs'],
  ['StockMarket', 'broad market moves — S&P 500, Nasdaq, Dow, rallies, selloffs'],
  ['Tech',        'AI, semiconductors, software, cloud — the tech industry broadly'],
  ['Crypto',      'bitcoin, ethereum, crypto markets and companies'],
  ['Energy',      'oil, gas, OPEC, renewables, energy prices'],
  ['Investing',   'personal investing, portfolios, dividends, ETFs, funds'],
];

// Threads only renders one hashtag as an actual clickable tag per post —
// anything beyond that just sits as flat, unlinked text, and Threads doesn't
// support cashtags ($TICKER) as a linkable entity at all (unlike X/Twitter).
// So emit exactly one hashtag: #TICKER if the story is mainly about a listed
// company, otherwise a topic tag, or none if nothing fits.
//
// The model picks the tag rather than keyword matching: substring matching
// tagged an NBA "smart balls" story #Earnings ("eps" inside "steps"), and even
// whole-word matching can't tell "Delta variant" from Delta Air Lines. The
// schema enum restricts it to known tags so it can't invent one.
const TICKER_TAGS = [...new Set(COMPANIES.map(([, ticker]) => ticker.replace('.', '')))];
const TOPIC_TAGS  = TOPICS.map(([tag]) => tag);
const NO_TAG      = 'none';

const HASHTAG_GUIDE = [
  'Companies (use the ticker): ' + COMPANIES.map(([name, t]) => `${name}=${t.replace('.', '')}`).join(', ') + '.',
  'Topics: ' + TOPICS.map(([tag, desc]) => `${tag} (${desc})`).join('; ') + '.',
].join('\n');

// ─── LLM rewording ─────────────────────────────────────────────────────────────

const anthropic = new Anthropic();

// Now that the feed is broad top-news rather than earnings-only, articles can
// legitimately sit for a while before this run picks them up (LIFO only
// guarantees "newest available", not "just happened") — an item can be
// several hours or close to the 72h MAX_AGE cutoff old. Without an explicit
// age cue the model has no way to know that and defaults to immediacy
// language ("just", "breaking"), which reads as wrong/stale-sounding once
// posted. Give it the actual elapsed time and an instruction tier so old-but-
// still-postable news gets retrospective framing instead.
function freshnessInstruction(pubDate) {
  if (!pubDate) return 'Publish time unknown — avoid words that assert exact timing either way ("just", "today", "breaking").';

  const hoursAgo = (Date.now() - pubDate.getTime()) / 3_600_000;
  if (hoursAgo <= 3) {
    return `This was reported about ${Math.round(hoursAgo)} hour(s) ago — recent enough that "just" / "breaking" framing is accurate if it fits.`;
  }
  if (hoursAgo <= 24) {
    return `This was reported about ${Math.round(hoursAgo)} hour(s) ago (earlier today/yesterday) — do NOT say "just happened" or "breaking". Neutral present-tense framing ("X is doing Y") is fine, but don't imply it just occurred.`;
  }
  const daysAgo = Math.round(hoursAgo / 24);
  return `This was reported about ${daysAgo} day(s) ago — this is OLD news, not breaking. Do NOT use "just", "breaking", "moments ago", or "today". Use clearly retrospective framing instead (e.g. "earlier this week", "X reported that...", past tense throughout).`;
}

// Returns { relevant, text, hashtag } — hashtag is '#TAG' or '' when nothing
// fits. The top-news feed carries politics/legal/sports stories too; without
// a way to say "skip this" the model wrote its reasoning ("This isn't a
// markets story…") into the post text, which then got posted.
async function rewordArticle(article) {
  const response = await anthropic.messages.create({
    model: 'claude-haiku-4-5',
    max_tokens: 500,
    system: [
      "You post on Threads for Stock Score, a stock market app for everyday retail investors — not a news outlet.",
      "Given a CNBC headline and summary, tell people what happened and why it matters, like you're texting a friend the headline, not filing a report.",
      "Lead with the concrete fact — the number, the move, the result — don't warm up with scene-setting.",
      "Short, punchy sentences. Contractions are fine. Avoid stiff financial-journalism words like \"marking\", \"amid\", \"underscores\", \"bolstering\", \"reflecting\", \"significant\".",
      "Do not copy phrases verbatim from the source — synthesize in your own words, don't paraphrase sentence-by-sentence.",
      "Every sentence must add a new fact or angle — never restate the same point in different words just to fill space. If there's nothing else worth saying, stop after one sentence.",
      "Factual only, never invent numbers or details not in the source.",
      "You may use at most one emoji if it genuinely fits (e.g. 📈📉🚀) — skip it entirely rather than force one.",
      'No hashtags in the post text, no quotation marks around it, no mention of "CNBC" or "according to".',
      "Match your tense and immediacy language to how old the story actually is — see the timing note below.",
      'Keep the post text under 320 characters.',
      "First decide whether the story is relevant to retail investors — markets, companies, business, the economy, rates, or policy with a clear market impact. If not (politics, legal, sports, entertainment, general news with no market angle), set relevant to false and leave text empty — never explain the decision in the text.",
      "Then pick ONE hashtag for the post. Use a company's ticker only if the story is mainly about that company (not a passing mention, and not a different meaning of the name — e.g. 'Delta variant' is not Delta Air Lines).",
      `Otherwise use the topic that genuinely fits, or "${NO_TAG}" if nothing fits clearly — a wrong tag is worse than none.`,
      '\n\n' + HASHTAG_GUIDE,
    ].join(' '),
    tools: [{
      name: 'submit_post',
      description: 'Submit the Threads post text and its hashtag.',
      input_schema: {
        type: 'object',
        properties: {
          relevant: { type: 'boolean', description: 'false if the story has no market/business angle and should not be posted.' },
          text:    { type: 'string', description: 'The post text, under 320 characters, no hashtags. Empty when relevant is false.' },
          hashtag: { type: 'string', enum: [...TICKER_TAGS, ...TOPIC_TAGS, NO_TAG], description: 'Tag without the # sign, or "none".' },
        },
        required: ['relevant', 'text', 'hashtag'],
      },
    }],
    tool_choice: { type: 'tool', name: 'submit_post' },
    messages: [
      {
        role: 'user',
        content: `Headline: ${article.title}\n\nSummary: ${article.description}\n\nTiming: ${freshnessInstruction(article.pubDate)}`,
      },
    ],
  });

  const toolBlock = response.content.find(b => b.type === 'tool_use');
  if (toolBlock?.input?.relevant === false) return { relevant: false };
  const text = toolBlock?.input?.text?.trim();
  if (!text) throw new Error('No post text in LLM response');
  const tag = toolBlock.input.hashtag;
  // Guard the enum anyway — an unknown tag is dropped rather than posted.
  const valid = TICKER_TAGS.includes(tag) || TOPIC_TAGS.includes(tag);
  return { relevant: true, text, hashtag: valid ? '#' + tag : '' };
}

function buildCaption(postText, hashtag) {
  const footer = hashtag ? '\n\n' + hashtag : '';
  const base = postText + footer;
  if (base.length <= CAPTION_LIMIT) return base;
  return postText.slice(0, CAPTION_LIMIT - footer.length - 1) + '…' + footer;
}

// ─── Threads ──────────────────────────────────────────────────────────────────

async function postToThreads(text) {
  const token  = process.env.THREADS_ACCESS_TOKEN;
  const userId = process.env.THREADS_USER_ID;
  const base   = `https://graph.threads.net/v1.0/${userId}`;

  const createResp = await fetch(`${base}/threads`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ media_type: 'TEXT', text, access_token: token }),
  });
  const { id, error } = await createResp.json();
  if (error) throw new Error(`Threads create error: ${error.message}`);

  await new Promise(r => setTimeout(r, 3000));

  const pubResp = await fetch(`${base}/threads_publish`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ creation_id: id, access_token: token }),
  });
  const pubData = await pubResp.json();
  if (pubData.error) throw new Error(`Threads publish error: ${pubData.error.message}`);
  return pubData.id;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const tracking = JSON.parse(readFileSync(TRACKING, 'utf8'));
  const posted   = new Set(tracking.posted);

  const resp = await fetch(CNBC_RSS_URL, { signal: AbortSignal.timeout(15000) });
  if (!resp.ok) throw new Error(`CNBC RSS feed responded ${resp.status}`);
  const xml = await resp.text();
  const items = parseRssItems(xml);

  if (items.length === 0) {
    console.log('No items returned from CNBC RSS feed.');
    return;
  }

  // Split into fresh (postable) vs. stale (too old — mark as seen so we
  // never retry them) among the articles we haven't posted yet.
  const now = Date.now();
  const freshCandidates = [];

  for (const item of items) {
    if (!item.link || posted.has(item.link)) continue;
    const pubDate = parsePubDate(item.pubDate);
    if (pubDate && now - pubDate.getTime() > MAX_AGE_MS) {
      console.log(`Skipping (older than ${MAX_AGE_HOURS}h): ${item.title}`);
      posted.add(item.link);
      continue;
    }
    freshCandidates.push({ ...item, pubDate });
  }

  // LIFO — newest fresh article first, so each run posts the latest headline.
  freshCandidates.sort((a, b) => (b.pubDate?.getTime() ?? now) - (a.pubDate?.getTime() ?? now));

  // Walk newest-first until the model accepts one. Off-topic stories are
  // marked as seen (only once we're actually posting — not on a dry run) so
  // they aren't re-checked every run.
  let article = null;
  let postText, hashtag;
  const offTopic = [];
  for (const candidate of freshCandidates.slice(0, MAX_RELEVANCE_CHECKS)) {
    console.log(`\nRewording: ${candidate.title}`);
    const result = await withRetry('LLM reword', () => rewordArticle(candidate));
    if (!result.relevant) {
      console.log('  Skipping (no market angle).');
      offTopic.push(candidate.link);
      continue;
    }
    article = candidate;
    ({ text: postText, hashtag } = result);
    break;
  }

  const isDryRun = !process.env.THREADS_ACCESS_TOKEN || !process.env.THREADS_USER_ID;
  if (!isDryRun) offTopic.forEach(link => posted.add(link));

  if (!article) {
    console.log('No fresh, market-relevant CNBC articles to post.');
    if (isDryRun) return;
    tracking.posted = [...posted].slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    return;
  }

  const caption = buildCaption(postText, hashtag);

  console.log('\n--- Threads post ---');
  console.log(caption);

  if (isDryRun) {
    console.log('\nNo Threads credentials — skipping post (dry run).');
    return;
  }

  try {
    const id = await withRetry('Threads', () => postToThreads(caption));
    console.log(`\n  ✓ Threads: ${id}`);
    posted.add(article.link);
    tracking.posted = [...posted].slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    console.log('Tracking file updated.');
  } catch (err) {
    console.error(`  ✗ Threads: ${err.message}`);
    process.exit(1);
  }

  console.log('\nDone.');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
