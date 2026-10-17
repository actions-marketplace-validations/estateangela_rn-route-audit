# Roadmap

Status as of 2026-10-17, after the v1.0.0 Marketplace listing. Opinions below are mine (the implementer's); items
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

## Published

v1.0.0 is live on the GitHub Marketplace as
[React Navigation Route Audit](https://github.com/marketplace/actions/react-navigation-route-audit).
Built outside work hours; the repository carries no company information and
shares 9% of its lines with the internal tool it was inspired by, all of it
syntax scaffolding.

**There are no users yet.** That is the single most important fact on this
page: every item below is a guess until someone who did not write it tries
it. Prefer anything that puts it in front of people over anything that adds
to it.

## Stage 1 -- preparing to publish

- [x] Configuration extracted (`Config` / CLI flags / action inputs).
      A `.yml` config file can wait until someone has more than four flags
      to set; flags are easier to document and to test.
- [x] No company information in the code.
- [x] Fresh repository, so no history to rewrite.
- [x] MIT.
- [x] Demo: `docs/terminal-demo.svg`, hand-authored rather than recorded --
      4 KB, sharp text, versionable, and a one-word fix instead of a re-record.
- **skip for now: rewrite in TypeScript.** This is the single largest piece
  of work on the original list and the least visible to users. What it buys:
  npm distribution and a JS Action. What it costs: a full rewrite, a
  `node_modules` toolchain, `ncc` bundling, and throwing away 38 tests that
  currently prove the parser's behaviour. A composite action calling Python
  works on every GitHub runner today. Revisit when there are users who want
  to `npm install` it, not before.

## Stage 2 -- Action MVP

- [x] Composite action, token-free (nothing to authenticate for route audit).
- [x] **PR comment on route changes.** `diff` subcommand plus
      `baseline-json` / `comment-file` action inputs, with a ready-to-copy
      workflow in `examples/pr-comment.yml`. Renames are one change, not a
      removal plus an addition.
- [x] `v1.0.0` tag and Marketplace listing.
- [ ] Set the Marketplace categories -- they are still empty, which is the
      cheapest discoverability fix available (Utilities / Code quality).
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

## What to do next, in order

1. **Set the Marketplace categories.** Two minutes, and nobody browsing
   finds the listing without them.
2. **Write up how it was built.** The story is better than a feature tour:
   the first design was invalidated by cloning four repositories, and a
   fixture test caught 13 wrong rows in a tool that had been running in
   production all day. This is the cheapest way to get the first users.
3. **Wait for an issue before building anything else.** We already have one
   recorded case of a confident assumption being wrong; the only thing that
   reduces that risk is someone else's project.

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
