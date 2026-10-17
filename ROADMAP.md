# Roadmap

Status as of 2026-10-17. Opinions below are mine (the implementer's); items
marked **skip** are ones I think cost more than they return and should be
argued for before being picked up.

## Done

- [x] Generic parser: three declaration styles (literal names, named
      constants, v7 static API), route-constants file optional
- [x] Validated against BlueWallet, Rocket.Chat.ReactNative,
      react-navigation's example app and one private production app --
      every `file` in the output exists in all four
- [x] Reverse lookup (exact / substring / normalized)
- [x] 38 tests, standard library only, three fixture apps covering every
      parsing case that has broken in practice
- [x] `action.yml` (composite), CI on Python 3.9 / 3.11 / 3.13 plus a
      self-test that runs the action against a fixture
- [x] MIT license, English docs

## Blocked on a decision, not on work

- [ ] **Permission to open source.** The parser was written on company time
      against a private codebase. Nothing company-specific remains in this
      repo (checked: no names, tickets, credentials, product copy), and the
      history starts fresh here, but publishing is still the employer's call.
      Everything below is pointless until this is settled.

## Stage 1 -- preparing to publish

- [x] Configuration extracted (`Config` / CLI flags / action inputs).
      A `.yml` config file can wait until someone has more than four flags
      to set; flags are easier to document and to test.
- [x] No company information in the code.
- [x] Fresh repository, so no history to rewrite.
- [x] MIT.
- [ ] Demo: a 30-second GIF of `lookup` is worth more than a sample app --
      the fixture apps already serve as runnable examples.
- **skip for now: rewrite in TypeScript.** This is the single largest piece
  of work on the original list and the least visible to users. What it buys:
  npm distribution and a JS Action. What it costs: a full rewrite, a
  `node_modules` toolchain, `ncc` bundling, and throwing away 38 tests that
  currently prove the parser's behaviour. A composite action calling Python
  works on every GitHub runner today. Revisit when there are users who want
  to `npm install` it, not before.

## Stage 2 -- Action MVP

- [x] Composite action, token-free (nothing to authenticate for route audit).
- [ ] **PR comment on route changes.** Highest value per hour on the whole
      list: comment "3 routes added, 1 renamed, 2 now behind a feature flag"
      on PRs that touch navigation. Needs the diff logic (exists, in the
      private repo) ported here. Does *not* need Figma.
- [ ] `v1` tag and Marketplace listing (after the permission question).
- **defer: everything Figma.** Worth being blunt: the Figma integration does
  not exist. Route names were put on frames by hand. Building it needs a
  frame-to-route convention that designers actually follow, a Figma token,
  the Images API for exports, and a gap report. It is the most interesting
  part of the idea and also the part with no code and no validated workflow
  yet. Build the route half first, get users, then design the Figma half
  against a real convention instead of an imagined one.

## Stage 3 -- more frameworks

- [ ] Adapter interface. The seam already exists (`find_jsx_screens`,
      `find_static_screens`); formalise it when adding the second framework,
      not before -- an interface designed against one implementation is
      usually wrong.
- [ ] Expo Router (file-system routing; a different shape of problem --
      directory walk rather than source parsing)
- [ ] Next.js App Router / Pages Router
- **skip: Vue Router, Nuxt, Flutter.** Each is a separate parsing problem
  (Flutter needs the Dart analyzer or codegen output). Three frameworks half
  supported is worse for the project's reputation than one supported well.
- [x] Use open-source projects as test material. This found the issue that
      invalidated the original design, so it should stay a habit: before
      claiming a pattern is supported, clone two projects that use it.

## Stage 4 -- output formats

- [x] JSON and CSV artifacts.
- [ ] Notion sync. Works in the private repo; porting it here means deciding
      whether this tool owns integrations or just emits data. Leaning
      towards: emit data, ship Notion as a documented recipe.
- **skip: public static search site.** For any real app the searchable text
  *is* product copy. GitHub Pages is public. The risk note on the original
  list is right, and the mitigation (Cloudflare Access) is a lot of moving
  parts for a feature a CSV already covers.

## Stage 5 and portfolio items

- [ ] **MCP server.** Small if the index is already JSON, and genuinely
      useful: an AI agent that knows which screen a route renders can stop
      guessing. Best value-per-hour of the portfolio items.
- [ ] npm CLI. Only after (and if) the TypeScript question is settled.
- [ ] Write-up of the development process. There is a real story here: the
      first design was invalidated by cloning four repos, and a fixture test
      caught 13 wrong rows in a tool that had been running in production all
      day. That is more interesting than a feature tour.
- **skip: monorepo, docs site, coverage badges, Changesets.** These signal
  scale the project does not have yet. One clear README and a green CI badge
  are more credible on a 1500-line tool than a VitePress site.

## Known limitations (documented, not bugs)

- Route params: one route can render very different screens depending on
  params. Reported as one route.
- Runtime navigation: only static declarations are seen.
- Strings assembled at runtime are not collected.
