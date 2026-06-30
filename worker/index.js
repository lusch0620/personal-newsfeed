// Cloudflare Worker — newsfeed-ai
// Routes:
//   POST /ask      — Haiku inline article Q&A
//   POST /brief    — Sonnet + web search, cited talking points
//   POST /discover — Sonnet + web search, RSS feed recommendations

const ALLOWED_ORIGIN = 'https://lusch0620.github.io';
const HAIKU   = 'claude-haiku-4-5-20251001';
const SONNET  = 'claude-sonnet-4-6';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin':  ALLOWED_ORIGIN,
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
  });
}

async function callAnthropic(apiKey, payload) {
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key':         apiKey,
      'anthropic-version': '2023-06-01',
      'Content-Type':      'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Anthropic ${resp.status}: ${err}`);
  }
  return resp.json();
}

function extractText(content) {
  // Return the last text block from a message content array
  const texts = content.filter(b => b.type === 'text');
  return texts.length ? texts[texts.length - 1].text : '';
}

function parseJSON(text) {
  const cleaned = text.trim().replace(/^```json\s*/i, '').replace(/\s*```$/, '');
  try { return JSON.parse(cleaned); }
  catch { return null; }
}

// ── /ask ─────────────────────────────────────────────────────────────────────
async function handleAsk(req, apiKey) {
  const { question, article } = await req.json();
  if (!question) return json({ error: 'question required' }, 400);

  const msg = await callAnthropic(apiKey, {
    model: HAIKU,
    max_tokens: 400,
    system: `You are answering questions for Lucius Gao, a Senior FIG analyst at Cantor Fitzgerald. \
He is technically fluent and understands finance deeply. Be direct, precise, and brief. No filler.`,
    messages: [{
      role: 'user',
      content: `Article: "${article.title}" (${article.source})
Summary: ${article.summary}
Talking points: ${(article.talking_points || []).join('; ')}

Question: ${question}`,
    }],
  });

  return json({ answer: extractText(msg.content) });
}

// ── /brief ────────────────────────────────────────────────────────────────────
async function handleBrief(req, apiKey) {
  const { topic, articles } = await req.json();
  if (!topic) return json({ error: 'topic required' }, 400);

  const context = (articles || []).slice(0, 5)
    .map(a => `- ${a.title} (${a.source}): ${a.summary}`)
    .join('\n');

  const msg = await callAnthropic(apiKey, {
    model: SONNET,
    max_tokens: 1200,
    tools: [{ type: 'web_search_20250305', name: 'web_search', max_uses: 3 }],
    system: `You are briefing Lucius Gao, a Senior FIG analyst at Cantor Fitzgerald. \
He needs cited, precise talking points for a specific topic — the kind he can use in a client call or an internal update. \
Return ONLY valid JSON in this exact shape, no markdown wrapper:
{"lede":"one crisp sentence on the core development","points":[{"claim":"...","source":"Publication Name","url":"https://..."}]}
3–5 points. Each claim must be self-contained and specific (include names, numbers, or dates). \
Only cite sources you actually found — no fabrications.`,
    messages: [{
      role: 'user',
      content: `Topic: ${topic}\n\nContext from his feed:\n${context}\n\nReturn JSON only.`,
    }],
  });

  const result = parseJSON(extractText(msg.content));
  return json(result || { lede: topic, points: [] });
}

// ── /discover ─────────────────────────────────────────────────────────────────
async function handleDiscover(req, apiKey) {
  const { topics, sources } = await req.json();
  if (!topics?.length) return json({ sources: [] });

  const topicList  = topics.slice(0, 8).join(', ');
  const sourceList = (sources || []).slice(0, 20).join(', ');

  const msg = await callAnthropic(apiKey, {
    model: SONNET,
    max_tokens: 2000,
    tools: [{ type: 'web_search_20250305', name: 'web_search', max_uses: 5 }],
    system: `You are finding high-quality RSS feeds for Lucius Gao, a Senior FIG analyst at Cantor Fitzgerald. \
His coverage: US banks (regional + money center), fintech, RIA/wealth management, insurance, specialty finance, PE deals, \
credit markets, capital markets. He targets a lateral move to a bulge-bracket FIG team or financial-services PE.

Search the web to find real, working RSS/Atom feed URLs. Verify each one exists before including it.

Return ONLY valid JSON in this exact shape, no markdown:
{"sources":[{"name":"...","rss_url":"https://...","description":"one sentence","why":"why this fits his topics","lane":"banks|aw|ins|sf|pe|markets|news|learn"}]}

Rules:
- rss_url must be a real, publicly accessible RSS or Atom feed URL (not a website homepage)
- Aim for 6–10 sources across his top topics
- Prefer specialist / institutional publications over general news
- Avoid sources already in his feed
- "why" should reference his specific engaged topics`,
    messages: [{
      role: 'user',
      content: `My highest-engagement topics (what I actually read and interact with): ${topicList}

I already have these sources — do NOT suggest them: ${sourceList}

Search for 6–10 RSS feeds I am missing. Focus on the highest-signal sources for each topic. Return JSON only.`,
    }],
  });

  const result = parseJSON(extractText(msg.content));
  return json(result || { sources: [] });
}

// ── Router ────────────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url  = new URL(request.url);
    const path = url.pathname;
    const key  = env.ANTHROPIC_API_KEY;

    if (!key) return json({ error: 'ANTHROPIC_API_KEY not set' }, 500);

    try {
      if (request.method === 'POST') {
        if (path === '/' || path === '/ask')  return handleAsk(request, key);
        if (path === '/brief')                return handleBrief(request, key);
        if (path === '/discover')             return handleDiscover(request, key);
      }
      return json({ error: 'not found' }, 404);
    } catch (e) {
      return json({ error: e.message }, 500);
    }
  },
};
