# Take‑Home Assignment: Trip Planner ChatGPT App (Apps SDK + MCP)

## Goal

Build a **ChatGPT App** (MCP server + UI widget) that provides a **Trip Planning tool**. ChatGPT should be able to invoke your tool to answer prompts like:

1. “I am traveling to Japan for 10 days and it will be my first time there. Can you build me a detailed itinerary that balances nature and cultural visit? I would love something that feels realistic and not rushed.”
2. “I am planning a 7 day trip to Italy with my partner and we want a mix of culture food and relaxation. Can you create an itinerary that covers Rome Florence and the Amalfi Coast with travel time included?”
3. “I am going to the US West Coast for 12 days on a solo trip. Can you build me an itinerary that includes major highlights local spots and some hidden gems while keeping things flexible?”

Your app must return **structured data** and render an **interactive UI** in ChatGPT with a **map showing destination points**. (Map can be Mapbox, MapLibre, Leaflet, or similar.)

You **do not** need to build real recommendation algorithms — **mock data is fine** — but you must design the tool schemas as if this were a real integration.

## Timebox

* Spend **no more than 5 hours**.
* If you hit 5 hours, **stop and submit what you have** (unfinished is OK).
* Strongly encouraged: use AI tools to accelerate development (see “AI usage” section).

## Tech & References

You may start from scratch or use a template.

Helpful references:

* Apps SDK docs: [https://developers.openai.com/apps-sdk](https://developers.openai.com/apps-sdk) ([OpenAI Developers][1])
* Apps SDK UI library: [https://openai.github.io/apps-sdk-ui/](https://openai.github.io/apps-sdk-ui/) ([OpenAI GitHub][2])
* Apps SDK UI repo: [https://github.com/openai/apps-sdk-ui](https://github.com/openai/apps-sdk-ui) ([GitHub][3])
* Example end-to-end Apps SDK apps: [https://github.com/openai/openai-apps-sdk-examples](https://github.com/openai/openai-apps-sdk-examples) ([GitHub][4])
* Apps SDK quickstart (shows `window.openai` and `openai/outputTemplate` patterns): [https://developers.openai.com/apps-sdk/quickstart](https://developers.openai.com/apps-sdk/quickstart) ([OpenAI Developers][5])
* Suggested starter template: [https://github.com/alpic-ai/apps-sdk-template](https://github.com/alpic-ai/apps-sdk-template) ([GitHub][6])

## What you’re building

### 1) MCP server (tool backend)

Implement an MCP server that exposes:

* A `/mcp` endpoint (streaming HTTP / StreamableHTTP is fine).
* A tool: **`trip.plan`** (or similar action-oriented name).

Your server must also register a UI “template” resource for the widget:

* The widget resource should be served with MIME type **`text/html+skybridge`** so ChatGPT treats it as a widget template. ([OpenAI Developers][7])
* The tool must reference the widget via `_meta["openai/outputTemplate"]` so ChatGPT renders it after tool calls. ([OpenAI Developers][5])

The widget will read tool results via `window.openai.toolOutput`. ([OpenAI Developers][5])

### 2) Tool schema design (input + output)

You must define:

* A structured **input schema** for the trip planning tool
* A structured **output schema** for the returned trip plan

Even if your MCP SDK only requires `inputSchema` at registration time, you should still implement an **explicit output schema** in code (e.g., Zod) and ensure your handler returns data conforming to it (type-safety + runtime validation is a plus). Apps SDK tool design emphasizes clear inputs and predictable outputs. ([OpenAI Developers][8])

### 3) Data source: `cities.json`

You'll be given a `cities.json` file containing place metadata (use it to populate names + coordinates + any tags you need).

You may:

* Filter/select destinations from `city.json`
* Or ignore "smart recommendations" and return a few deterministic mock destinations that *match the prompt shape*
* But your tool output must include valid place metadata from `cities.json` (at least for the map points)

### 4) UI widget (frontend inside ChatGPT)

Build a UI widget component that renders in ChatGPT:

* Reads data from `window.openai.toolOutput` ([OpenAI Developers][5])
* Displays:

  * A trip summary panel (origin, dates/season, duration, budget)
  * A list of destinations / itinerary items
  * A map with markers for the destination point(s) (and ideally origin)

Map library:

* Your choice: Mapbox, MapLibre, Leaflet, etc.
* Prefer a setup that works without paid keys; if you require a token, document it clearly in README.

Optional (nice to have):

* A “Regenerate plan” or “Adjust budget” button that triggers a new tool call from the widget using `window.openai.callTool`. ([OpenAI Developers][5])

UI components:

* Optional but recommended: use Apps SDK UI components for basic styling/controls consistency. ([GitHub][3])

Tip: There is an official example “Map” component in the Apps SDK examples gallery you can reference for patterns like plotting geo data and selection panes. ([OpenAI Developers][9])

## Local testing requirements

You do **not** need to deploy a production server, but you can test your app in following ways:

* **MCP Inspector testing steps** (preferred baseline)
  The MCP Inspector can be run via `npx` and provides a UI to call tools and inspect schemas/results. ([modelcontextprotocol.io][10])
* **ChatGPT developer mode testing**
  ChatGPT supports connecting to your MCP server in developer mode; it requires an **HTTPS** endpoint (tunneling via ngrok/Cloudflare Tunnel is acceptable). ([OpenAI Developers][11])

(If you use Chrome and you can’t see widget UI locally, note there are known Chrome flag issues described in the examples repo; you can mention any workaround you used in README.) ([GitHub][4])

## Deliverables

Please submit:

1. A git repo (or zip) containing:

   * MCP server code
   * Widget UI code
   * `cities.json` usage (readme explains where it lives)
2. A `README.md` with:

   * Install + run instructions
   * How to test tool calls (Inspector instructions or ChatGPT dev mode)
   * Example prompts to try (include the 3 prompts above)
3. **Schemas** clearly defined in code (input + output)
4. (Optional) screenshot / short video / GIF of the widget running

## AI usage (required)

Use as much AI as you want.

Include an `AI_USAGE.md` describing:

* Which AI tools you used (ChatGPT, Copilot, Cursor, etc.)
* Roughly what you used them for (schema design, boilerplate, map integration, debugging)
* Any key prompts that shaped the solution (short summary is fine)


[1]: https://developers.openai.com/apps-sdk?utm_source=chatgpt.com "Apps SDK - developers.openai.com"
[2]: https://openai.github.io/apps-sdk-ui/?utm_source=chatgpt.com "Introduction - Apps SDK UI - openai.github.io"
[3]: https://github.com/openai/apps-sdk-ui?utm_source=chatgpt.com "GitHub - openai/apps-sdk-ui"
[4]: https://github.com/openai/openai-apps-sdk-examples "GitHub - openai/openai-apps-sdk-examples: Example apps for the Apps SDK"
[5]: https://developers.openai.com/apps-sdk/quickstart "Quickstart"
[6]: https://github.com/SohniSwatantra/apps-sdk-template "GitHub - SohniSwatantra/apps-sdk-template: Generated from alpic-ai/apps-sdk-template"
[7]: https://developers.openai.com/apps-sdk/build/mcp-server "Build your MCP server"
[8]: https://developers.openai.com/apps-sdk/plan/tools "Define tools"
[9]: https://developers.openai.com/apps-sdk/plan/components "Design components"
[10]: https://modelcontextprotocol.io/docs/tools/inspector "MCP Inspector - Model Context Protocol"
[11]: https://developers.openai.com/apps-sdk/deploy/connect-chatgpt "Connect from ChatGPT"
