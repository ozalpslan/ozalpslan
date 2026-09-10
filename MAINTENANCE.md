# Maintaining this profile

This repository is the source for `github.com/ozalpslan`'s profile README. It must be published as the public repository `ozalpslan/ozalpslan` to appear on the profile. The native GitHub contribution calendar is managed by GitHub; this README does not modify it.

## Artwork

`assets/glasshouse-mark.svg` preserves the silhouette of the GlassHouse logo supplied for this profile. The brand artwork belongs to GlassHouse. The README identifies this as Alper's personal profile and states his internship role.

The header uses cyan `#00B2EF`, magenta `#ED0090` and yellow `#F8EE02`. Its letters and arc positions stay fixed. Each arc holds its color for 3.2 seconds, then transitions for 0.8 seconds. One cycle takes 12 seconds. Light, dark, animated and static headers are generated together. The README selects the static version for reduced-motion preferences.

Build the artwork from its editable sources with Python 3.10 or later (no third-party runtime packages):

```sh
python3 scripts/profile.py build
python3 -m unittest discover -s tests -v
```

## Activity data

The workflow refreshes the last 31 calendar days, including the current UTC day, at approximately 04:17 UTC daily. GitHub may delay scheduled runs. Counts represent contributions, not only commits. Only data accessible to the repository's built-in `GITHUB_TOKEN` is requested; private repository details are never requested or stored.

The workflow also runs on its initial publication, generator/workflow updates and manual dispatch. It uses the built-in token with `contents: write` to save the chart and its dated source data. Its updates are authored by `github-actions[bot]` and do not create artificial user contributions. No personal token, external chart host or separate deployment is required.

For a local live refresh, provide `GH_TOKEN` or `GITHUB_TOKEN` through the environment and run:

```sh
python3 scripts/profile.py refresh --username ozalpslan
```

Missing credentials, API errors, malformed responses and incomplete date ranges fail the refresh before changing the existing charts. The last successful data and visible refresh timestamp remain available. Before the first successful fetch, the chart explicitly displays a pending state. A cached initial snapshot can also come from the user's public GitHub contribution calendar; its provenance is recorded in `assets/activity.json`.

GitHub disables scheduled workflows in public repositories after 60 days without repository activity. If refreshing stops, check the Actions tab, re-enable the workflow if necessary and run it manually. A failing run remains visible in Actions; the graph's date range exposes stale data.

## Publication

The local repository can be reviewed before publication. Publish only when the owner explicitly requests it. Confirm the remote is `https://github.com/ozalpslan/ozalpslan.git`; check for existing remote content before creating or updating the public repository. Do not overwrite an existing profile or change another repository's visibility.

After publication, check the first workflow run and inspect the profile in light and dark mode. Rolling back the README or header assets restores the earlier design. Disabling the activity workflow freezes the last chart.
