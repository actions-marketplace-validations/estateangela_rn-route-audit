# I cloned four apps to check my own assumption. Three of them broke it.

*How a QA script became a GitHub Action, and what measuring real projects
cost me.*

---

## The problem nobody files a ticket for

A designer and a developer look at the same screen and have no shared name
for it. The designer calls it "the amount step". The developer knows it as
`Checkout/Amount`. Analytics reports a third thing. The bug ticket describes
it in prose.

Nothing fails. There is no error, no red build, no incident. Everyone just
spends a minute at the start of every design review, every bug report and
every handoff working out which screen is being discussed. The cost is
invisible precisely because it never breaks anything.

I am a QA engineer on a mobile app with 172 routes. I wanted one thing: a
page where somebody could type the words they can see on a screen and get
the route name back.

## Version one: the obvious design

Our app declares route names in one file:

```tsx
// src/router/path.tsx
export const HomePath = 'Main/Home'
export const CheckoutAmountPath = 'Checkout/Amount'
```

and mounts them like this:

```tsx
<Screen name={CheckoutAmountPath} component={CheckoutAmountScreen} />
```

So the design wrote itself. Read the constants file, find the `<Screen>`
that uses each constant, resolve the component to a file, pull the `t('…')`
keys out of that file, look them up in the translations. Now you can search
by on-screen text.

It worked. It ran in CI twice a day, synced to a page the designers use, and
posted to Slack when routes changed. Done.

Then I decided to open source the generic part, and that is where it got
interesting.

## The question I nearly skipped

Before publishing I asked myself a question that was easy to answer with a
shrug: *will this work on anyone else's project?*

I could have reasoned about it. Instead I cloned four React Navigation
projects and counted how screens are actually declared:

| Project | `name={Constant}` | `name="Literal"` | v7 static API |
|---|--:|--:|--:|
| BlueWallet | 0 | **114** | 0 |
| Rocket.Chat.ReactNative | 0 | 0 | **147** |
| react-navigation (its own example app) | 7 | **1462** | **1057** |
| Our app | **191** | 0 | 0 |

My entire design rested on the pattern that appears in exactly one of the
four — mine.

Worse, Rocket.Chat does not use JSX screens at all. It uses React
Navigation v7's static API:

```tsx
createNativeStackNavigator({
  screens: { ShareListView: ShareListViewScreen, ShareView },
})
```

There is no `<Screen>` tag to find and no `name=` attribute to read. My tool
would have scanned 1,680 files and reported zero routes.

On three of the four projects, the first version of this tool produced an
empty table — or a `FileNotFoundError`, because it required a route
constants file that most projects simply do not have.

Had I published without measuring, the first person to try it would have run
it, got nothing, and closed the tab. There is no second impression.

## The fix was not "support more formats"

The temptation was to add two more parsers and move on. The actual problem
was that the data flowed the wrong way:

```
before:  route constants file  →  find the screen that uses each one
after:   every screen declaration  →  that is the route list
```

Route names come from the screen declarations themselves. The constants
file, when a project has one, becomes optional enrichment: it resolves
`name={HomePath}` to `'Main/Home'` and supplies group headings. When it is
missing, nothing breaks.

That one inversion is what turned a tool for my codebase into a tool.

| Project | Routes found now |
|---|--:|
| BlueWallet | 92 |
| Rocket.Chat.ReactNative | 87 |
| react-navigation example app | 71 |
| Our app | 184 |

In all four, every file path in the output points at a file that exists.

## The part that actually stung

To support the other patterns I needed a fixture app — a tiny React
Navigation project in the test suite, with one file per case I claimed to
handle.

I wrote it with `<Stack.Screen name={HomePath} …>`, the namespaced form. Ran
the tests. **Every route came back as unmounted.**

The regex was `<(\w*Screen)`. `\w` does not match `.`, so `<Stack.Screen>`
never matched at all. One character class, and the scanner silently skipped
an entire syntax.

Then I checked our production app, the one that had been running happily in
CI:

```
<Screen            185
<Tab.Screen          4
<BottomTab.Screen    2
```

Six screens had never been parsed. I had reported them as "declared but
never mounted", written that into the documentation as expected behaviour,
and explained to my team why those five routes were fine. They were not
fine. They were mounted — in `<Tab.Screen>` — and I had told everyone
otherwise.

While I was in there I found a second bug. Conditional mounts look like
this:

```tsx
{flags.betaEnabled && (
  <Screen name={BetaPath} component={BetaScreen} />
)}
```

Those screens are unreachable when the flag is off, which for QA is the
difference between a test case existing and not existing. I detected them by
scanning back fifteen lines for the last `&&`. A conditional block that had
already closed above a screen got attributed to it — and a screen inside a
block that opened more than fifteen lines up got missed.

The error ran in both directions:

- **six** screens that *are* behind a feature flag were reported as always
  reachable. Our test plan had no flag-off cases for them.
- **two** screens that are unconditional were reported as flagged.

Thirteen rows wrong, in a tool that had been in production for a day,
producing numbers that looked entirely reasonable. The fixture caught all of
it in under a second, and only because I wrote the fixture in a style
different from my own codebase.

The fix is to require proof: a condition counts only if its opening brace is
still unclosed at the screen's position.

## What I would tell myself at the start

**Measure before generalising.** "Will this work elsewhere?" took me forty
minutes to answer with four `git clone`s. I had been about to answer it with
a shrug. Everything that followed — the redesign, the two bugs, the thirteen
wrong rows — came out of those forty minutes.

**Write fixtures in a style you did not write.** A fixture that mirrors your
own code only proves your tool handles your code. Mine found a real bug on
its first run specifically because I typed `<Stack.Screen>` out of habit
instead of the `<Screen>` our codebase uses.

**A tool that runs clean is not a tool that is right.** Green CI, plausible
numbers, happy users, thirteen wrong rows. Nothing in the system was capable
of noticing.

**Name the manual step.** The tool does not write into Figma. A designer
looks up the route and pastes it onto the frame themselves. Automating that
would need a naming convention every designer already follows, and agreeing
that convention is the hard part — a tool cannot do it for you. Saying so
plainly is better than implying an integration that does not exist.

---

The result is [rn-route-audit](https://github.com/estateangela/rn-route-audit),
on the [GitHub Marketplace](https://github.com/marketplace/actions/react-navigation-route-audit).
It audits routes, reverse-looks-up a route from text on screen, comments on
pull requests that change navigation, and writes a single self-contained
HTML page for people who do not run code. 56 tests, no dependencies.

Every parsing case in those tests is there because it broke something first.
