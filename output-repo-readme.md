# kindle-dash-output

Auto-generated image store for [kindle-dash](https://github.com/travismorton1995/kindle-dash).

This repo holds the current `dash.png` — the rendered dashboard a
jailbroken Kindle Paperwhite 4 fetches and draws — plus `weather.json`, the
last good weather response, which the next render falls back to if the
weather API is unreachable. Both are force-pushed as a fresh single commit
on every render, this README included, so there's no history to speak of
and nothing here should be edited by hand.

It's a separate, private repo from the code on purpose: `kindle-dash` itself
is public (free unlimited GitHub Actions minutes), but the rendered image
contains real calendar event titles — effectively a live schedule — so it
stays somewhere that isn't world-readable.

See the main repo for setup, architecture, and everything else.
