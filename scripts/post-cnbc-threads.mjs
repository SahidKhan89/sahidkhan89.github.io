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
  || 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135';
const TRACKING    = new URL('../data/posted_cnbc_threads.json', import.meta.url).pathname;
const MAX_HISTORY = 500;
const CAPTION_LIMIT = 500; // Threads character limit
const MAX_AGE_HOURS = 72;  // don't post news older than this
const MAX_AGE_MS = MAX_AGE_HOURS * 60 * 60 * 1000;

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

const TOPICS = [
  ['Earnings',    ['earnings', 'eps', 'revenue', 'profit', 'quarterly', 'beat', 'miss', 'guidance', 'outlook']],
  ['Economy',     ['economy', 'economic', 'gdp', 'recession', 'unemployment', 'jobs', 'payroll']],
  ['Fed',         ['federal reserve', 'fomc', 'interest rate', 'rate cut', 'rate hike', 'powell']],
  ['Inflation',   ['inflation', 'cpi', 'pce', 'deflation', 'tariff', 'tariffs']],
  ['StockMarket', ['stock market', 'equity', 'rally', 'selloff', 'bull market', 'bear market', 's&p', 'nasdaq', 'dow']],
  ['Tech',        ['artificial intelligence', 'ai ', 'semiconductor', 'chip', 'software', 'cloud']],
  ['Crypto',      ['bitcoin', 'crypto', 'ethereum', 'blockchain', 'btc', 'eth']],
  ['Energy',      ['oil', 'crude', 'opec', 'natural gas', 'renewables', 'solar']],
  ['Investing',   ['investing', 'portfolio', 'dividend', 'yield', 'etf', 'fund']],
];

// Threads only renders one hashtag as an actual clickable tag per post —
// anything beyond that just sits as flat, unlinked text, and Threads doesn't
// support cashtags ($TICKER) as a linkable entity at all (unlike X/Twitter).
// So emit exactly one hashtag: the ticker as #TICKER if the article names a
// company (more specific and more useful for a stock account), otherwise the
// top topic tag.
function generateHashtags(title, description) {
  const lower = (title + ' ' + description).toLowerCase();
  const full  = title + ' ' + description;

  for (const [name, ticker] of COMPANIES) {
    if (full.includes(name)) return '#' + ticker.replace('.', '');
  }

  for (const [tag, keywords] of TOPICS) {
    if (keywords.some(kw => lower.includes(kw))) return '#' + tag;
  }

  return '';
}

// ─── LLM rewording ─────────────────────────────────────────────────────────────

const anthropic = new Anthropic();

async function rewordArticle(article) {
  const response = await anthropic.messages.create({
    model: 'claude-haiku-4-5',
    max_tokens: 300,
    system: [
      "You post on Threads for Stock Score, a stock market app for everyday retail investors — not a news outlet.",
      "Given a CNBC headline and summary, tell people what happened and why it matters, like you're texting a friend the headline, not filing a report.",
      "Lead with the concrete fact — the number, the move, the result — don't warm up with scene-setting.",
      "Short, punchy sentences. Contractions are fine. Avoid stiff financial-journalism words like \"marking\", \"amid\", \"underscores\", \"bolstering\", \"reflecting\", \"significant\".",
      "Do not copy phrases verbatim from the source — synthesize in your own words, don't paraphrase sentence-by-sentence.",
      "Every sentence must add a new fact or angle — never restate the same point in different words just to fill space. If there's nothing else worth saying, stop after one sentence.",
      "Factual only, never invent numbers or details not in the source.",
      "You may use at most one emoji if it genuinely fits (e.g. 📈📉🚀) — skip it entirely rather than force one.",
      'No hashtags, no quotation marks around the output, no mention of "CNBC" or "according to".',
      'Under 320 characters. Output ONLY the post text — nothing else.',
    ].join(' '),
    messages: [
      {
        role: 'user',
        content: `Headline: ${article.title}\n\nSummary: ${article.description}`,
      },
    ],
  });

  const textBlock = response.content.find(b => b.type === 'text');
  if (!textBlock) throw new Error('No text in LLM response');
  return textBlock.text.trim();
}

function buildCaption(postText, article) {
  const hashtags = generateHashtags(article.title, article.description);
  const footer = hashtags ? '\n\n' + hashtags : '';
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

  const article = freshCandidates[0];
  if (!article) {
    console.log('No fresh CNBC articles to post.');
    tracking.posted = [...posted].slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    return;
  }

  console.log(`\nRewording: ${article.title}`);
  const postText = await withRetry('LLM reword', () => rewordArticle(article));
  const caption  = buildCaption(postText, article);

  console.log('\n--- Threads post ---');
  console.log(caption);

  if (!process.env.THREADS_ACCESS_TOKEN || !process.env.THREADS_USER_ID) {
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
