/**
 * AgentSoul Demo Worker
 * Deployed at: demo.agentsoul.dev
 *
 * Acts as a live AgentSoul agent for a fictional auto shop demo.
 * Calls Claude Haiku to generate responses — fast and cheap.
 *
 * Secrets required (Cloudflare dashboard → Worker → Settings → Variables):
 *   ANTHROPIC_API_KEY = sk-ant-...
 */

const SYSTEM_PROMPT = `You are an AgentSoul demo agent deployed at Mesa Auto & Tire, a fictional auto shop in Boise, Idaho. You have access to the shop's internal documents and can answer questions quickly and accurately.

You are demonstrating what AgentSoul does: a private AI agent that knows a business's own documents and answers staff and customer questions instantly — without sending data to the cloud.

Keep replies short and conversational. 2–4 sentences max. Sound helpful and knowledgeable, not robotic.

Sample knowledge you have access to:
- Oil change: $49.95 synthetic / $29.95 conventional — about 45 minutes
- Tire rotation: $19.95 (free when combined with oil change)
- Brake inspection: free. Pad replacement starts at $149/axle
- Alignment check: $29.95, full alignment $89.95
- Hours: Monday–Saturday 7:30am–6:00pm, closed Sunday
- Warranty: 12 months / 12,000 miles on all labor
- Payment: cash and all major cards accepted, no personal checks
- Owner: Mike Carrillo, 15 years in business, 8 bays, 6 full-time techs

If someone asks something outside your knowledge, say you'd need to check with the team and offer to have someone follow up. Never invent prices or policies beyond what's listed above.

If someone asks what you are or how you work, explain briefly: you're an AgentSoul agent — a private AI that runs on local hardware inside the business, trained on their documents, and never sends data anywhere.`;

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default {
  async fetch(request, env) {

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    let message;
    try {
      const body = await request.json();
      message = (body.message || '').trim();
    } catch {
      return errorResponse('Invalid request body.');
    }

    if (!message) {
      return errorResponse('No message provided.');
    }

    // Soft rate limit: reject very long inputs
    if (message.length > 500) {
      return jsonResponse({ response: 'Please keep your question under 500 characters for the demo.' });
    }

    try {
      const anthropicRes = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': env.ANTHROPIC_API_KEY,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 300,
          system: SYSTEM_PROMPT,
          messages: [{ role: 'user', content: message }],
        }),
      });

      if (!anthropicRes.ok) {
        const err = await anthropicRes.text();
        console.error('Anthropic error:', err);
        return errorResponse('The demo agent is having trouble right now. Try again in a moment.');
      }

      const data = await anthropicRes.json();
      const reply = data?.content?.[0]?.text ?? 'No response generated.';

      return jsonResponse({ response: reply });

    } catch (err) {
      console.error('Worker error:', err);
      return errorResponse('Unexpected error. Please try again.');
    }
  }
};

function jsonResponse(body) {
  return new Response(JSON.stringify(body), {
    headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
  });
}

function errorResponse(message) {
  return new Response(JSON.stringify({ response: message }), {
    status: 500,
    headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
  });
}
