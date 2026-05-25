import { readFileSync, writeFileSync } from 'fs';

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
      ? new Date(article.provider_publish_time).toISOString()
      : '',
  });
  return `${CARD_BACKEND_URL}/market-news/card-image?${p.toString()}`;
}

async function warmCardImage(imageUrl) {
  try {
    console.log('  [card] warming image URL…');
    const resp = await fetch(imageUrl, { signal: AbortSignal.timeout(25000) });
    const size = resp.headers.get('content-length') ?? '?';
    console.log(`  [card] warm-up status: ${resp.status} (${size} bytes)`);
    if (!resp.ok) {
      console.warn(`  [card] backend unavailable (${resp.status}) — will post text-only`);
      return false;
    }
    return true;
  } catch (err) {
    console.warn(`  [card] warm-up failed: ${err.message} — will post text-only`);
    return false;
  }
}

// ─── X (Twitter) ─────────────────────────────────────────────────────────────

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

// ─── Reddit ───────────────────────────────────────────────────────────────────

async function getRedditToken() {
  const { REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD } = process.env;
  const resp = await fetch('https://www.reddit.com/api/v1/access_token', {
    method:  'POST',
    headers: {
      Authorization: 'Basic ' + Buffer.from(`${REDDIT_CLIENT_ID}:${REDDIT_CLIENT_SECRET}`).toString('base64'),
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent':   `nodejs:market-news-bot:v1.0 (by /u/${REDDIT_USERNAME})`,
    },
    body: new URLSearchParams({ grant_type: 'password', username: REDDIT_USERNAME, password: REDDIT_PASSWORD }),
  });
  const data = await resp.json();
  if (!data.access_token) throw new Error(`Reddit auth failed: ${JSON.stringify(data)}`);
  return data.access_token;
}

async function uploadImageToReddit(token, username, imageUrl) {
  // Fetch the card image
  const imgResp = await fetch(imageUrl, { signal: AbortSignal.timeout(25000) });
  if (!imgResp.ok) throw new Error(`Failed to fetch card image: ${imgResp.status}`);
  const imgBytes = Buffer.from(await imgResp.arrayBuffer());

  // Get S3 upload lease from Reddit
  const leaseResp = await fetch('https://oauth.reddit.com/api/media/asset.json', {
    method:  'POST',
    headers: {
      Authorization:  `Bearer ${token}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent':   `nodejs:market-news-bot:v1.0 (by /u/${username})`,
    },
    body: new URLSearchParams({ filepath: 'card.jpg', mimetype: 'image/jpeg' }),
  });
  const lease = await leaseResp.json();
  if (!lease.asset?.upload_lease) throw new Error(`Reddit media lease error: ${JSON.stringify(lease)}`);

  const { action, fields } = lease.asset.upload_lease;
  const uploadUrl = action.startsWith('//') ? `https:${action}` : action;

  // Upload bytes to S3
  const form = new FormData();
  for (const { name, value } of fields) form.append(name, value);
  form.append('file', new Blob([imgBytes], { type: 'image/jpeg' }), 'card.jpg');
  const s3Resp = await fetch(uploadUrl, { method: 'POST', body: form });
  if (s3Resp.status !== 201) throw new Error(`S3 upload failed: ${s3Resp.status}`);

  return lease.asset.websocket_url;
}

async function postToReddit(article, caption, imageUrl) {
  const { REDDIT_USERNAME, REDDIT_SUBREDDIT } = process.env;
  const token = await getRedditToken();

  // Upload card image to Reddit's hosting
  const websocketUrl = await uploadImageToReddit(token, REDDIT_USERNAME, imageUrl);

  // Submit as image post (title capped at Reddit's 300-char limit)
  const submitResp = await fetch('https://oauth.reddit.com/api/submit', {
    method:  'POST',
    headers: {
      Authorization:  `Bearer ${token}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent':   `nodejs:market-news-bot:v1.0 (by /u/${REDDIT_USERNAME})`,
    },
    body: new URLSearchParams({
      sr:        REDDIT_SUBREDDIT,
      kind:      'image',
      title:     article.title.slice(0, 300),
      url:       websocketUrl,
      api_type:  'json',
      resubmit:  'true',
      ...(process.env.REDDIT_FLAIR_ID && { flair_id: process.env.REDDIT_FLAIR_ID }),
    }),
  });
  const submitData = await submitResp.json();
  const errors = submitData?.json?.errors;
  if (errors?.length) throw new Error(`Reddit submit error: ${JSON.stringify(errors)}`);

  const postName = submitData?.json?.data?.name; // e.g. "t3_abc123"

  // Add caption + article link as the first comment (standard pattern for image posts)
  if (postName) {
    await new Promise(r => setTimeout(r, 3000));
    await fetch('https://oauth.reddit.com/api/comment', {
      method:  'POST',
      headers: {
        Authorization:  `Bearer ${token}`,
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent':   `nodejs:market-news-bot:v1.0 (by /u/${REDDIT_USERNAME})`,
      },
      body: new URLSearchParams({
        thing_id: postName,
        text:     `${caption}\n\n${article.link}`,
        api_type: 'json',
      }),
    });
  }

  return submitData?.json?.data?.url ?? 'posted';
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

  // Find the first unposted article whose card image is available, skip bad ones
  const candidates = news.filter(a => a.link && !posted.has(a.link));
  if (candidates.length === 0) {
    console.log('No new articles to post.');
    return;
  }

  let article = null;
  let activeImageUrl = null;

  for (const candidate of candidates) {
    const imageUrl = cardImageUrl(candidate);
    console.log(`\nTrying: ${candidate.title}`);
    const imageReady = await warmCardImage(imageUrl);
    if (imageReady) {
      article = candidate;
      activeImageUrl = imageUrl;
      break;
    }
    // Card image failed — mark as seen so we don't retry it next run
    console.log(`  [skip] adding to posted list to avoid retrying.`);
    posted.add(candidate.link);
  }

  if (!article) {
    console.log('\nNo articles with a working card image found this run.');
    // Save the skipped articles so they're not retried
    tracking.posted = [...posted].slice(-MAX_HISTORY);
    writeFileSync(TRACKING, JSON.stringify(tracking, null, 2) + '\n');
    console.log('Tracking file updated (skipped articles recorded).');
    return;
  }

  console.log(`\nPosting: ${article.title}`);
  console.log(`Source:  ${article.publisher}`);

  const threadsText = buildCaption(article, 500);
  const igText      = buildCaption(article, 2200);
  const redditText  = buildCaption(article, 500);

  console.log('\n--- Threads caption ---');
  console.log(threadsText);

  const results = await Promise.allSettled([
    process.env.THREADS_ACCESS_TOKEN
      ? withRetry('Threads', () => postToThreads(threadsText, activeImageUrl))
      : Promise.resolve('skipped — no credentials'),

    (process.env.IG_ACCESS_TOKEN && process.env.IG_USER_ID)
      ? withRetry('Instagram', () => postToInstagram(igText, activeImageUrl))
      : Promise.resolve('skipped — no credentials'),

    (process.env.REDDIT_CLIENT_ID && process.env.REDDIT_SUBREDDIT)
      ? withRetry('Reddit', () => postToReddit(article, redditText, activeImageUrl))
      : Promise.resolve('skipped — no credentials'),
  ]);

  const platforms = ['Threads', 'Instagram', 'Reddit'];
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
