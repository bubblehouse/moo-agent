## [1.6.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.5.0...v1.6.0) (2026-05-18)

### Features

* **zil_import:** add [@quit](https://gitlab.com/quit) verb to Zork Actor ([4633e59](https://gitlab.com/bubblehouse/moo-agent/commit/4633e59adf7a39115053370fefddc891fff88a2c))
* **zil_import:** native realtime scheduler and $zork_actor_npc class ([fcf2de4](https://gitlab.com/bubblehouse/moo-agent/commit/fcf2de41f896b287b5abef8558dbbf80e0497245))

### Bug Fixes

* **zil_import:** cover translator gaps surfaced by zork1 shakedown ([9161bb3](https://gitlab.com/bubblehouse/moo-agent/commit/9161bb3c37e193ed617937bb74ba33dee58ac62a))
* **zil_import:** expand zork1 reset-state coverage (water level, broken lamp, junk invisible) ([9348cd7](https://gitlab.com/bubblehouse/moo-agent/commit/9348cd7483bed583afc5e561f699b4ce8b22971b))
* **zil_import:** substrate verb fixes for take/throw/push/look ([a82bb27](https://gitlab.com/bubblehouse/moo-agent/commit/a82bb2706b8bdc63e35585e0210229b2143b1a3d))
* **zil_import:** zork1 verb fixes for i_thief, pot_of_gold, diagnose ([d608e8f](https://gitlab.com/bubblehouse/moo-agent/commit/d608e8fbd11b56269b5ea99b4e825b16fc306f52))

## [1.5.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.4.0...v1.5.0) (2026-05-17)

### Features

* **agent:** enable Anthropic prompt caching on system prompt ([440ab04](https://gitlab.com/bubblehouse/moo-agent/commit/440ab043c893301ef57e3a73c52b84439bc01ab2))

### Bug Fixes

* **brain/chain:** tolerate +site suffix in reconnect-page token names ([f04326d](https://gitlab.com/bubblehouse/moo-agent/commit/f04326d5c6067ca1ee6d6af16baeed3cb3821c4b))
* **brain:** detect verb-test mistakes and track burrow target rooms ([35a196e](https://gitlab.com/bubblehouse/moo-agent/commit/35a196ea419d5e154f80b2cda9651102002a2078))

## [1.4.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.3.0...v1.4.0) (2026-05-12)

### Features

* **agent:** add use_baseline flag to skip baseline merge for self-contained souls ([e57d96a](https://gitlab.com/bubblehouse/moo-agent/commit/e57d96a9a2b8141266776415ded5507ce6799815))
* **agents:** add gamer, a solo Zork I explorer for zork1.local ([703842a](https://gitlab.com/bubblehouse/moo-agent/commit/703842a4873e5ca6a207d21382bf2233a058b671))
* **bootstrap:** regenerated zork1 bootstrap from extras/zil_import ([72ad889](https://gitlab.com/bubblehouse/moo-agent/commit/72ad889dd3738ebbc5d3586192a5cb88a093841e))
* **bootstrap:** regenerated zork1 bootstrap from extras/zil_import ([3fc770f](https://gitlab.com/bubblehouse/moo-agent/commit/3fc770f2c280644483dbcfb9c685822f2cb13e26))
* **skills:** zork-shakedown skill for driving the zork1 smoke and bootstrap ([a5b8d9e](https://gitlab.com/bubblehouse/moo-agent/commit/a5b8d9e6afbd01e9d2aa5cfe325bf60d2a0e87a9))
* **zil_import:** compound-look + bare-drop rewrites, pronoun resolution, take-all containment ([f74ce04](https://gitlab.com/bubblehouse/moo-agent/commit/f74ce0416f1ad35ef113bb2ce9363f7f5dc33014))
* **zil_import:** hand-written verb templates overriding auto-translator output ([9805178](https://gitlab.com/bubblehouse/moo-agent/commit/9805178384a0f6c4d1cc4cda0c6fdd61426830c0))
* **zil_import:** per-object dspec, PRE-X return guards, exit-condition overrides, handwritten-template skip ([75c0599](https://gitlab.com/bubblehouse/moo-agent/commit/75c05990e7bf693a7f56ec98c9192c0f93dd27c9))
* **zil_import:** translate ZIL source into a DjangoMOO bootstrap package ([c4dddc8](https://gitlab.com/bubblehouse/moo-agent/commit/c4dddc8ff231f046ee16573413c235d8990d9b09))

### Bug Fixes

* **agent:** loop detector ignores movement commands during exploration ([d976375](https://gitlab.com/bubblehouse/moo-agent/commit/d9763755dc2fbc07ba67a50bd20dcc9f74745abf))
* **ci:** clone django-moo for release job and drop dev deps from shipped requirements.txt ([1feb91c](https://gitlab.com/bubblehouse/moo-agent/commit/1feb91ceccf85846e6e45aebb3cd8aa8451c5206))
* **ci:** scope pylint to moo/agent so it doesn't trip on the moo/ namespace root ([b0837b7](https://gitlab.com/bubblehouse/moo-agent/commit/b0837b78dd066513df8fb7b3bd5fa08fb5c89938))
* **ci:** shallow-clone django-moo so uv sync can resolve the path source ([c089e9b](https://gitlab.com/bubblehouse/moo-agent/commit/c089e9b4189dd8af92b1998a331f2f879abcade0))

## [1.3.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.2.0...v1.3.0) (2026-05-02)

### Features

* **brain:** auto-extract room IDs from divine() output ([52253ac](https://gitlab.com/bubblehouse/moo-agent/commit/52253acdcd019f2986aec783fe2d55a927ace9f1))
* **connection:** add IAC telnet negotiation support ([40fb8d9](https://gitlab.com/bubblehouse/moo-agent/commit/40fb8d9e43adfd692fccf58796815b02a7611429))

### Bug Fixes

* **connection:** send "a11y quiet on" instead of the removed QUIET verb ([8e743ed](https://gitlab.com/bubblehouse/moo-agent/commit/8e743ed4d92bbede359367670b928eed1f71fb77))
* **tools:** allow parens in quoted args of bare tool calls ([c9ee2a8](https://gitlab.com/bubblehouse/moo-agent/commit/c9ee2a8147d71d2e0dbe28f5865f93bc5e5c97b7))

## [1.2.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.1.0...v1.2.0) (2026-04-18)

### Features

* **agents:** add take/drop tools to Warden and Archivist, place tool to Stocker ([1c648de](https://gitlab.com/bubblehouse/moo-agent/commit/1c648de46b1da9c73b6521b66caa2ad9569abd5c))
* **agents:** use placement and container tools in Tinker and Quartermaster ([5ec00db](https://gitlab.com/bubblehouse/moo-agent/commit/5ec00db47de83c2ca6164d22c3e40f8624d39ae2))
* **brain:** drop standalone XML-tag-only lines in directive parsing ([25c41a2](https://gitlab.com/bubblehouse/moo-agent/commit/25c41a25811a2a9d9c4e3b2c54207e2ed01573d5))
* **brain:** extend redundant-teleport guard to the bare-line fallback ([e462cc4](https://gitlab.com/bubblehouse/moo-agent/commit/e462cc4bd0e62076a3d30c46fc49788722f966c7))
* **brain:** track current room and guard redundant teleport tool calls ([eb85b3e](https://gitlab.com/bubblehouse/moo-agent/commit/eb85b3ed98978ed8baece1e4fa217442590c4d01))
* **tools:** add place, open, close, put, take, drop as registered tools ([a7339cb](https://gitlab.com/bubblehouse/moo-agent/commit/a7339cb73a76fa8d2d1d71365c8816b77b042a9e))
* **warden:** randomize dark rooms during inspection pass ([763ed77](https://gitlab.com/bubblehouse/moo-agent/commit/763ed773072572d81bb893b8321967a0d70caa1d))

### Bug Fixes

* **agentmux:** force-restart PID-alive agents whose logs are silent past STALE_SECONDS ([685525d](https://gitlab.com/bubblehouse/moo-agent/commit/685525d38471bd7f1203f35e13b22e593da6df4e))
* **warden:** require grant_write before setting dark property ([f0683f9](https://gitlab.com/bubblehouse/moo-agent/commit/f0683f9a970981a7a8292cc1b4debfc3f3e8d4e0))

## [1.1.0](https://gitlab.com/bubblehouse/moo-agent/compare/v1.0.0...v1.1.0) (2026-04-17)

### Features

* **agents:** add makers group config with pre_start board-clear hook ([051f61b](https://gitlab.com/bubblehouse/moo-agent/commit/051f61b89afc15cdf5c2ee5dff72eec8cd446446))
* **quartermaster:** add placement cycle and SOUL.patch.md lessons ([cde58c0](https://gitlab.com/bubblehouse/moo-agent/commit/cde58c0d59437da28201cf9410fc5626dfd36d92))
* **tinker:** add required placement section with [@move](https://gitlab.com/move) vs place distinction ([e4545fc](https://gitlab.com/bubblehouse/moo-agent/commit/e4545fcb71c072f86e54f4556d4fac57dc340eb9))

## 1.0.0 (2026-04-16)

### Features

* add a foreman agent to coordinate the rest ([e879474](https://gitlab.com/bubblehouse/moo-agent/commit/e879474e5827261c2be39e62a63525eb7fdef5f1))
* add agentmux restart <name> for single-agent restart by name ([7bebb9d](https://gitlab.com/bubblehouse/moo-agent/commit/7bebb9d2ce604dfab2bfb27f28962fbe56d3cd6c))
* add compass to look output, agent fixes, tests ([c68d191](https://gitlab.com/bubblehouse/moo-agent/commit/c68d191181b2aca9d81274edb18e13ff4c34a642))
* added agent support for local inference....one day ([a901549](https://gitlab.com/bubblehouse/moo-agent/commit/a901549c99bbfd405947abb11fd8b5e06d207420))
* added cliff and newman agents for mail system testing ([53c8d51](https://gitlab.com/bubblehouse/moo-agent/commit/53c8d51627b4cc1defa33a95b5d10df04f4d5b06))
* added tool use support to moo-agent ([e8c4efa](https://gitlab.com/bubblehouse/moo-agent/commit/e8c4efab17190898fc2a81b9f3644886c000a46a))
* **agent:** add MOO_TOKEN_CHAIN env override, dynamic agentmux layout, token chain auto-relay ([bd1246e](https://gitlab.com/bubblehouse/moo-agent/commit/bd1246e317187e9b85b2258b83617bc742b6fba4))
* **agent:** add temperature config and wire it through to LLM calls ([ada44e6](https://gitlab.com/bubblehouse/moo-agent/commit/ada44e6b4acfa3c903406fd6d983ba0dd45834d8))
* **agent:** add timer_only and clear_window_on_wakeup config options ([b493586](https://gitlab.com/bubblehouse/moo-agent/commit/b493586ecb7d0c5bc7195c851afc7489b6e6a1e8))
* **agent:** add token chain auto-relay, dynamic agentmux layout, MOO_TOKEN_CHAIN env override ([2a357bf](https://gitlab.com/bubblehouse/moo-agent/commit/2a357bfd45f4d0017806241f08cb4a320480bdcb))
* **agent:** cache orchestrator flag at startup and skip post-drain LLM cycles for orchestrators ([ed74dea](https://gitlab.com/bubblehouse/moo-agent/commit/ed74deac7cab456306349c008dfc314c6cb66807))
* **agent:** instrument LLM cycles and add adaptive stall check via agentmux cycle-age ([c2c4f31](https://gitlab.com/bubblehouse/moo-agent/commit/c2c4f3183dc6e0c351d956702ba0b59980101cbf))
* **agent:** parse [Mail] inbox lines on token receipt, add send_report tool ([0220461](https://gitlab.com/bubblehouse/moo-agent/commit/0220461892197ade514e1ecd01aed1549bcc67c3))
* **agent:** plumb 'of' parameter through divine tool wrapper ([044b571](https://gitlab.com/bubblehouse/moo-agent/commit/044b5710a0203df57335ecb3d542b1c74914ab27))
* **agent:** rename coordination tools to post_board/read_board/write_book/read_book/clear_topic, drop room-list injection ([bc5d19c](https://gitlab.com/bubblehouse/moo-agent/commit/bc5d19c84345548891dd46889f90b3321c6b06ae))
* **agents:** add inspectors, neighbours, wanderer agent groups ([3815ed3](https://gitlab.com/bubblehouse/moo-agent/commit/3815ed36a9f571b0bbcb927fe0d0c40750e0eaec))
* configure tradesmen agents into iterative loop ([c6424dc](https://gitlab.com/bubblehouse/moo-agent/commit/c6424dcb7bcc6ea28ce6ac7c93b87c58da1ed4f9))
* expose new navigation verbs as agent tool specs ([7796f61](https://gitlab.com/bubblehouse/moo-agent/commit/7796f614aeaa5a0fc71e7ff9b3f3f409c17a3a01))
* implemented moo-agent for autonomous experiments ([ed0c55f](https://gitlab.com/bubblehouse/moo-agent/commit/ed0c55fdd1fd60861085d9428a24fc507c398f9e))
* split builder agent into mutiple simpler agents ([885a339](https://gitlab.com/bubblehouse/moo-agent/commit/885a3398a957391a451f25a9c634a377f8175863))
* support Bedrock in moo-agent ([865b4df](https://gitlab.com/bubblehouse/moo-agent/commit/865b4df4eb04423cf542251a00a03492ef1ffa76))

### Bug Fixes

* add teleport-to syntax, look-at global lookup, huh2 cardinal aliases, coerce tool args to str ([df76cb5](https://gitlab.com/bubblehouse/moo-agent/commit/df76cb5d24438ada2ac1bca7aafd01d9690b775c))
* added stocker agent for consumables, other agent updates ([4096bcb](https://gitlab.com/bubblehouse/moo-agent/commit/4096bcbe3d1403aa5ccb19c04ebaff5dd2fb7edc))
* after a script, print a summary of what you did ([e185a7d](https://gitlab.com/bubblehouse/moo-agent/commit/e185a7d4c255a89d776c159c54646351821259af))
* agent should pre-generate a list of commands rather than doing each one by one ([d2d8451](https://gitlab.com/bubblehouse/moo-agent/commit/d2d8451fa306a0641adb2dc50c6a6e8f0db7b6e1))
* agent stall on non-response ([1543547](https://gitlab.com/bubblehouse/moo-agent/commit/1543547084e0e47170d6ab6aa229434f885d8dde))
* agent updates to self-train after mistakes ([653be56](https://gitlab.com/bubblehouse/moo-agent/commit/653be56769364af9321fed3410909fe267b94f49))
* **agent:** add command-loop detector, remove stale check_inbox queuing, and broaden special-token regex ([a68bdba](https://gitlab.com/bubblehouse/moo-agent/commit/a68bdbaa77dd4f6dbbf184b363df19f9cd402eb2))
* **agent:** detect page verb in both conjugations for they/them players ([bdf785a](https://gitlab.com/bubblehouse/moo-agent/commit/bdf785a3efde27b523666a11832a93707ef1c2d0))
* **agentmux:** correctly stop a single named agent without killing the whole group ([ab58a58](https://gitlab.com/bubblehouse/moo-agent/commit/ab58a586400bce15a3f7e0f658abe57db3e1be6c))
* **agent:** normalize bare integer object references in tool arg translation ([57a5103](https://gitlab.com/bubblehouse/moo-agent/commit/57a5103720860e0f7297455a69e10fef0afc69dd))
* **agent:** set current_goal on [Done] Blocked and relay token as 'Token: X go.' to avoid LLM misreading prior agent's completion message ([0adcfca](https://gitlab.com/bubblehouse/moo-agent/commit/0adcfca70e64957164661b9dcdc21cc0c575c3e5))
* **agents:** harden warden master key handling and reorder inspectors token chain ([9abaa04](https://gitlab.com/bubblehouse/moo-agent/commit/9abaa0420d55d932cd6b793b213a9f4196b4d3c1))
* **agents:** reduce Foreman stall timeout to 180s based on observed P95 runtimes and update token chain order ([eaec79d](https://gitlab.com/bubblehouse/moo-agent/commit/eaec79d53a721e0e342cb01a8ee3d7a90b658a1e))
* **agents:** restore LM Studio settings, fix Harbinger SOUL, improve alias guidance ([582cf9d](https://gitlab.com/bubblehouse/moo-agent/commit/582cf9d92e8a7fdb6b2064e41d463e4cdc26fc60))
* **agents:** switch to claude-sonnet-4-6, cap harbinger NPC spawn rate to 10% ([b3c534f](https://gitlab.com/bubblehouse/moo-agent/commit/b3c534f19852d82e28f9d2bb5a2f8696bf183fbc))
* **agent:** strip endoftext token leakage from LM Studio responses ([1094d5c](https://gitlab.com/bubblehouse/moo-agent/commit/1094d5c8f7b6dfc03ab159b12c52e90ff6af8d04))
* **agent:** strip Harmony special tokens from LLM output and resumed logs ([a4481c1](https://gitlab.com/bubblehouse/moo-agent/commit/a4481c19d091c34c503734515401c5d95cc92f9d))
* **agent:** suppress prior session summary for all page-triggered agents to prevent stale context injection ([b32a25d](https://gitlab.com/bubblehouse/moo-agent/commit/b32a25d801f99458b44c5e9427911ad546fad448))
* brain updates for gemma ([5b97e45](https://gitlab.com/bubblehouse/moo-agent/commit/5b97e4510a58d4118be4cc5c39f57ec2c3ee7869))
* **build:** use packages=moo for correct PEP 420 namespace wheel layout ([9bcc3d9](https://gitlab.com/bubblehouse/moo-agent/commit/9bcc3d924461241b9db83288cdf56b799372d38b))
* **ci:** add package.json for semantic-release npm tooling ([177d361](https://gitlab.com/bubblehouse/moo-agent/commit/177d36116539e674aec76a821c53504f7e9ef09d))
* **ci:** add pylint-gitlab to dev dependencies for lint reporters ([3ed1bf5](https://gitlab.com/bubblehouse/moo-agent/commit/3ed1bf55619e765b11e301ac49026c7a9e6a3513))
* **ci:** consolidate jobs and fix sdist/dev-dep issues ([6118fc6](https://gitlab.com/bubblehouse/moo-agent/commit/6118fc6b61e5eeead80a42762ded4f6beff2d544))
* created agentmux script for agent-trainer ([88953fa](https://gitlab.com/bubblehouse/moo-agent/commit/88953fa5a51c9f90481006628cb465e3bf457256))
* dont display output separators ([3d2f35b](https://gitlab.com/bubblehouse/moo-agent/commit/3d2f35b8e560af8e314e4e7c8e8bbc2ed8dc2189))
* dont silently discard extra markdown blocks ([0d8cf12](https://gitlab.com/bubblehouse/moo-agent/commit/0d8cf12d57f70b02f6a9342839366809a70299be))
* eagerly flush the buffer so content doesnt get lost by the agent ([88730fc](https://gitlab.com/bubblehouse/moo-agent/commit/88730fcde8a64ab1a7542efa99449ce46b40715f))
* encourage agent to pre-generate a script of commands it needs to run ([38606be](https://gitlab.com/bubblehouse/moo-agent/commit/38606bebdb26acb4cc04bf3be56033f6b440ef43))
* futher agent bugs ([76661e8](https://gitlab.com/bubblehouse/moo-agent/commit/76661e8a0c23828d3496a87748864b2ce67a1496))
* handle ssh reconnection and other agent issues ([15bb3c9](https://gitlab.com/bubblehouse/moo-agent/commit/15bb3c93127025f485770b3d7949835989b6d560))
* improve agent context and resume behavior ([7de25a7](https://gitlab.com/bubblehouse/moo-agent/commit/7de25a70848cef136266a00b9970d99cf9b6687a))
* improve agent permission and multiuser performance ([49ba120](https://gitlab.com/bubblehouse/moo-agent/commit/49ba12053a52b8a9e5baffda34bbbd2c3199e9db))
* improve agent text handling ([e3b80f5](https://gitlab.com/bubblehouse/moo-agent/commit/e3b80f5715c75c74d565c77b22aba022be7278b0))
* improved agent token handling, test updates ([40a9609](https://gitlab.com/bubblehouse/moo-agent/commit/40a9609b3a8164f871a502dc422e3e7f42ab01ab))
* more agent edge cases ([34165ec](https://gitlab.com/bubblehouse/moo-agent/commit/34165ec1e93456c76aba552acaf59d965083b477))
* more agent edge cases ([9c09861](https://gitlab.com/bubblehouse/moo-agent/commit/9c09861afba6ba08b17839afa8ff5936114efdf1))
* more agent training ([485ab2f](https://gitlab.com/bubblehouse/moo-agent/commit/485ab2f5b321111240f3390c37654ec5df0d8217))
* more agent tuning ([3b039d1](https://gitlab.com/bubblehouse/moo-agent/commit/3b039d19eb8e04b76fd88ef052870af0f90a04f2))
* more agent tuning ([2cf257d](https://gitlab.com/bubblehouse/moo-agent/commit/2cf257d2bfca06753ac2a6991ed294891d652a00))
* more script handling issues ([1812182](https://gitlab.com/bubblehouse/moo-agent/commit/1812182d433c99ea7a98c36086a1044434046270))
* more scroll handling, other agent fixes ([1e8534b](https://gitlab.com/bubblehouse/moo-agent/commit/1e8534b69034d4702813f1ba6b7c880d9eda79da))
* mypy typing errors ([6256f90](https://gitlab.com/bubblehouse/moo-agent/commit/6256f9085b9dedaafe0a0c8117d5651110de5811))
* post-run agent updates ([40d9842](https://gitlab.com/bubblehouse/moo-agent/commit/40d98424b31b2a688b4a5b5ae1e80fa73f719bf6))
* refactored agent baseline knowledge, created new unused stocker agent ([3d2e7bf](https://gitlab.com/bubblehouse/moo-agent/commit/3d2e7bfbd25fe45fa9defa44d8095c3f37c99d6a))
* scroll handling in agent TUI ([091d0dc](https://gitlab.com/bubblehouse/moo-agent/commit/091d0dcc56780d0131b9755e5c760aaf963bacd8))
* shell and [@edit](https://gitlab.com/edit) edge-case handling, agent fixes ([4e25888](https://gitlab.com/bubblehouse/moo-agent/commit/4e258887fd4927156eb7100ce101fef2467aa347))
* style update ([bfe9908](https://gitlab.com/bubblehouse/moo-agent/commit/bfe9908d87cb3c0f618354e631b650c4c59bfaee))
* **tests:** update locked container assertion and add missing _FakeSSHConfig to brain tests ([73b1fa8](https://gitlab.com/bubblehouse/moo-agent/commit/73b1fa860d346edb66bf8d3f89de4c9000212f7a))
* try to translate bare tool-call syntax before sending as MOO command ([c946386](https://gitlab.com/bubblehouse/moo-agent/commit/c94638689bf8dbe069a72478c57dee3da1b9b3cf))
* use bedrock by default, other startup fixes ([b0c7c35](https://gitlab.com/bubblehouse/moo-agent/commit/b0c7c3569e26ee6ec9b5d47b244166cf562be720))
* **verbs:** remove drop/take/get aliases from container/thing dispatch to prevent ambiguity ([31e6df3](https://gitlab.com/bubblehouse/moo-agent/commit/31e6df3454272ab5ce8f9ef76d70640979f68f01))
