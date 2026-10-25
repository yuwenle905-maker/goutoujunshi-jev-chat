import http from 'node:http';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {ApiError, authenticate, messagesFor, ReplyService} from './core.mjs';

const BASE = 'https://api.deepseek.com';
async function deepseek(path, key, body) {
  if (!key) throw new ApiError(503, 'provider_key_missing');
  let response;
  try { response = await fetch(BASE + path, {method: body ? 'POST' : 'GET', headers: {Authorization: `Bearer ${key}`, 'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(45000), redirect: 'error'}); }
  catch { throw new ApiError(504, 'provider_unreachable'); }
  // Never forward provider error bodies or credentials to logs/client.
  if (!response.ok) throw new ApiError(response.status === 429 ? 429 : 502, `provider_http_${response.status}`);
  const data = await response.json().catch(() => { throw new ApiError(502, 'provider_invalid_response'); });
  return data;
}
export function createApp({token, apiKey = '', model = 'deepseek-flash', temperature = .9, provider, modelProvider, logger = console.log} = {}) {
  if (!token || token.length < 32 || token.startsWith('replace-')) throw new Error('Configure a random DEVICE_TOKEN of at least 32 characters');
  if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) throw new Error('TEMPERATURE must be between 0 and 2');
  // BYOK stays per request, never in the response cache or logs. Services are keyed by a one-way digest.
  const services = new Map(), rates = new Map();
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    let code = 'ok', status = 200;
    try {
      if (req.method === 'GET' && req.url === '/health') return res.end('{"status":"ok"}');
      authenticate(req.headers.authorization, token);
      const key = req.headers['x-deepseek-key'] || apiKey;
      if (typeof key !== 'string' || key.length > 256) throw new ApiError(400, 'invalid_key');
      const scope = createHash('sha256').update(key).digest('hex');
      const now = Date.now();
      if (rates.size > 100) rates.clear();
      const rate = rates.get(scope);
      const next = !rate || now - rate.start > 60000 ? {start: now, count: 1} : {...rate, count: rate.count + 1};
      rates.set(scope, next);
      if (next.count > 30) throw new ApiError(429, 'rate_limit');
      if (req.method === 'GET' && req.url === '/v1/models') {
        const data = modelProvider ? await modelProvider() : await deepseek('/models', key);
        const models = (data.data || []).map(x => x.id).filter(x => typeof x === 'string');
        return res.end(JSON.stringify({models}));
      }
      if (req.method !== 'POST' || req.url !== '/v1/reply') throw new ApiError(404, 'not_found');
      if (!req.headers['content-type']?.startsWith('application/json')) throw new ApiError(415, 'json_required');
      let bytes = 0, chunks = [];
      for await (const chunk of req) {
        bytes += chunk.length;
        if (bytes > 3000000) throw new ApiError(413, 'body_too_large');
        chunks.push(chunk);
      }
      let raw;
      try { raw = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new ApiError(400, 'invalid_json'); }
      raw.model ||= model;
      raw.temperature ??= temperature;
      let service = services.get(scope);
      if (!service) {
        if (services.size >= 8) throw new ApiError(503, 'credential_scope_limit');
        service = new ReplyService();
        services.set(scope, service);
      }
      const generate = provider || (async data => {
          const result = await deepseek('/chat/completions', key, {model: data.model, messages: messagesFor(data), temperature: data.temperature, thinking: {type: 'disabled'}, response_format: {type: 'json_object'}, max_tokens: 800, stream: false});
          const choice = result.choices?.[0];
          if (choice?.finish_reason !== 'stop' || typeof choice.message?.content !== 'string') throw new ApiError(502, 'model_incomplete');
          return choice.message.content;
        });
      res.end(JSON.stringify(await service.reply(raw, scope, generate)));
    } catch (e) {
      status = e instanceof ApiError ? e.status : 500;
      code = e instanceof ApiError ? e.code : 'internal_error';
      res.writeHead(status); res.end(JSON.stringify({error: code}));
    } finally {
      // No account, peer, body, key, URL query, or provider response content.
      logger(JSON.stringify({time: new Date().toISOString(), status, code}));
    }
  });
  server.requestTimeout = 60000; server.headersTimeout = 10000;
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const app = createApp({token: process.env.DEVICE_TOKEN, apiKey: process.env.DEEPSEEK_API_KEY, model: process.env.DEEPSEEK_MODEL, temperature:Number(process.env.TEMPERATURE ?? .9)});
  const port = Number(process.env.PORT || 8787);
  app.listen(port, process.env.HOST || '127.0.0.1', () => console.log(`Goutou API listening on ${port}`));
}
