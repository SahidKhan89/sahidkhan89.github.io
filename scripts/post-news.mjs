import { readFileSync, writeFileSync } from 'fs';
import { TwitterApi } from 'twitter-api-v2';

// ─── Config ──────────────────────────────────────────────────────────────────

const BACKEND_URL      = process.env.BACKEND_URL      || 'https://sahidkhan89.pythonanywhere.com';
const CARD_BACKEND_URL = process.env.CARD_BACKEND_URL || 'https://disturbed-melly-skhan89-05036d6c.koyeb.app';
const TRACKING    = new URL('../data/posted_articles.json', import.meta.url).pathname;
const MAX_HISTORY = 500;

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
];

const TOPICS = [
  ['Earnings',    ['earnings', 'eps', 'revenue', 'profit', 'quarterly', 'beat', 'miss', 'layoff']],
  ['Economy',     ['economy', 'economic', 'gdp', 'recession', 'unemployment', 'jobs', 'payroll']],
  ['Fed',         ['federal reserve', 'fomc', 'interest rate', 'rate cut', 'rate hike', 'powell']],
  ['Inflation',   ['inflation', 'cpi', 'pce', 'deflation', 'tariff', 'tariffs']],
  ['StockMarket', ['stock market', 'equity', 'rally', 'selloff', 'bull market', 'bear market', 's&p', 'nasdaq', 'dow']],
  ['Tech',        ['artificial intelligence', 'ai ', 'semiconductor', 'chip', 'software', 'cloud']],
  ['Crypto',      ['bitcoin', 'crypto', 'ethereum', 'blockchain', 'btc', 'eth']],
  ['Energy',      ['oil', 'crude', 'opec', 'natural gas', 'renewables', 'solar']],
  ['Investing',   ['investing', 'portfolio', 'dividend', 'yield', 'etf', 'fund']],
];

function generateHashtags(title, summary) {
  const lower = (title + ' ' + summary).toLowerCase();
  const full  = title + ' ' + summary;

  const topicTags = [];
  for (const [tag, keywords] of TOPICS) {
    if (keywords.some(kw => lower.includes(kw))) {
      topicTags.push('#' + tag);
      if (topicTags.length === 2) break;
    }
  }

  const companyTags = [];
  for (const [name, ticker] of COMPANIES) {
    if (full.includes(name)) {
      const tag = '$' + ticker;
      if (!companyTags.includes(tag)) companyTags.push(tag);
      if (companyTags.length === 1) break;
    }
  }

  return [...topicTags, ...companyTags].join(' ');
}

// ─── Caption builder ──────────────────────────────────────────────────────────
// Platform limits:  X = 280 chars  |  Threads = 500 chars  |  Instagram = 2200 chars

function buildCaption(article, maxChars) {
  const title    = article.title   || '';
  const summary  = article.summary || '';
  const hashtags = generateHashtags(title, summary);

  // Priority: title always first, hashtags always last, summary fills the gap
  const footer   = hashtags ? '\n\n' + hashtags : '';
  const base     = title + footer;

  if (base.length >= maxChars) {
    // Title alone won't fit — hard truncate
    return title.slice(0, maxChars - 1) + '…';
  }

  const summaryRoom = maxChars - base.length - 2; // -2 for the \n\n separator
  if (summaryRoom < 30 || !summary) {
    return base;
  }

  const summarySlice = summary.length > summaryRoom
    ? summary.slice(0, summaryRoom - 1) + '…'
    : summary;

  return title + '\n\n' + summarySlice + footer;
}

// ─── Card image URL ───────────────────────────────────────────────────────────

function cardImageUrl(article) {
  const p = new URLSearchParams({
    title:     article.title     || '',
    publisher: article.publisher || '',
    thumbnail: article.thumbnail || '',
    pubDate:   article.provider_publish_time
      ? new Date(article.provider_publish_time * 1000).toISOString()
      : '',
  });
  return `${CARD_BACKEND_URL}/market-news/card-image?${p.toString()}`;
}

// ─── X (Twitter) ─────────────────────────────────────────────────────────────

async function postToX(text, imageUrl) {
  const client = new TwitterApi({
    appKey:       process.env.X_API_KEY,
    appSecret:    process.env.X_API_SECRET,
    accessToken:  process.env.X_ACCESS_TOKEN,
    accessSecret: process.env.X_ACCESS_TOKEN_SECRET,
  });

  const trimmed = text.length > 275 ? text.slice(0, 272) + '…' : text;

  if (imageUrl) {
    // Download the card image and upload to Twitter
    const imgResp = await fetch(imageUrl, { signal: AbortSignal.timeout(20000) });
    if (!imgResp.ok) throw new Error(`Image download failed: ${imgResp.status}`);
    const imgBuffer = Buffer.from(await imgResp.arrayBuffer());
    const mediaId = await client.v1.uploadMedia(imgBuffer, { mimeType: 'image/jpeg' });
    const { data } = await client.v2.tweet({ text: trimmed, media: { media_ids: [mediaId] } });
    return data.id;
  }

  const { data } = await client.v2.tweet({ text: trimmed });
  return data.id;
}

// ─── Threads ──────────────────────────────────────────────────────────────────

async function postToThreads(text, imageUrl) {
  const token  = process.env.THREADS_ACCESS_TOKEN;
  const userId = process.env.THREADS_USER_ID;
  const base   = `https://graph.threads.net/v1.0/${userId}`;

  const body = {
    media_type:   imageUrl ? 'IMAGE' : 'TEXT',
    text,
    access_token: token,
  };
  if (imageUrl) body.image_url = imageUrl;

  const createResp = await fetch(`${base}/threads`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
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

// ─── Instagram ────────────────────────────────────────────────────────────────

async function postToInstagram(caption, imageUrl) {
  if (!imageUrl) throw new Error('Instagram requires an image');

  const token  = process.env.IG_ACCESS_TOKEN;
  const userId = process.env.IG_USER_ID;

  // Step 1: create media container
  const mediaResp = await fetch(`https://graph.instagram.com/v23.0/${userId}/media`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ image_url: imageUrl, caption, access_token: token }),
  });
  const mediaData = await mediaResp.json();
  if (mediaData.error) throw new Error(`IG media error: ${mediaData.error.message}`);
  const creationId = mediaData.id;

  await new Promise(r => setTimeout(r, 2000));

  // Step 2: publish
  const pubResp = await fetch(`https://graph.instagram.com/v23.0/${userId}/media_publish`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ creation_id: creationId, access_token: token }),
  });
  const pubData = await pubResp.json();
  if (pubData.error) throw new Error(`IG publish error: ${pubData.error.message}`);
  return pubData.id;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const tracking = JSON.parse(readFileSync(TRACKING, 'utf8'));
  const posted   = new Set(tracking.posted);

  // Fetch news from yfinance backend
  const resp = await fetch(`${BACKEND_URL}/market-news`, { signal: AbortSignal.timeout(15000) });
  if (!resp.ok) throw new Error(`Backend responded ${resp.status}`);
  const { news } = await resp.json();

  if (!news || news.length === 0) {
    console.log('No news returned from backend.');
    return;
  }

  // Pick the most recent article that hasn't been posted yet
  const article = news.find(a => a.link && !posted.has(a.link));
  if (!article) {
    console.log('No new articles to post.');
    return;
  }

  console.log(`\nPosting: ${article.title}`);
  console.log(`Source:  ${article.publisher}`);

  const xText      = buildCaption(article, 280);
  const threadsText = buildCaption(article, 500);
  const igText      = buildCaption(article, 2200);
  const imageUrl    = await cardImageUrl(article);

  console.log('\n--- X caption ---');
  console.log(xText);
  console.log('\n--- Threads caption ---');
  console.log(threadsText);

  const results = await Promise.allSettled([
    process.env.X_API_KEY
      ? postToX(xText, imageUrl)
      : Promise.resolve('skipped — no credentials'),

    process.env.THREADS_ACCESS_TOKEN
      ? postToThreads(threadsText, imageUrl)
      : Promise.resolve('skipped — no credentials'),

    (process.env.IG_ACCESS_TOKEN && process.env.IG_USER_ID)
      ? postToInstagram(igText, imageUrl)
      : Promise.resolve('skipped — no credentials'),
  ]);

  const platforms = ['X', 'Threads', 'Instagram'];
  let anySuccess = false;
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      console.log(`  ✓ ${platforms[i]}: ${r.value}`);
      anySuccess = true;
    } else {
      console.error(`  ✗ ${platforms[i]}: ${r.reason?.message}`);
    }
  });

  if (anySuccess) {
    posted.add(article.link);
    tracking.posted = [...posted].slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    console.log('\nTracking file updated.');
  }

  console.log('\nDone.');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
