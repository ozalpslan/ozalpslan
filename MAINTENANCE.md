# Maintaining this profile

This repository is the source for `github.com/ozalpslan`'s profile README. It must be published as the public repository `ozalpslan/ozalpslan` to appear on the profile. The native GitHub contribution calendar is managed by GitHub; this README does not modify it.

## Artwork

`assets/glasshouse-mark.svg` preserves the silhouette of the GlassHouse logo supplied for this profile. The brand artwork belongs to GlassHouse. The README identifies this as Alper's personal profile and states his internship role.

The unframed, transparent header places **Alper Özarslan**, the **Linux & DevOps Platform Intern** title and a short introduction on the left, with the GH logo at the upper right. The mobile version uses shorter text lines and a smaller mark. The toolbox, yearly graph and links align with the introduction below it. Introductory copy is generated in `header()` in `scripts/profile.py`; keep the README image's alternative text in sync when editing it.

The logo uses cyan `#00B2EF`, magenta `#ED0090` and yellow `#F8EE02`. Its letters and arc positions stay fixed. Each arc holds its color for 0.55 seconds, then transitions for 0.45 seconds. One cycle takes 3 seconds. Light, dark, animated and static headers are generated together. The README selects the static version for reduced-motion preferences.

Build the artwork from its editable sources with Python 3.10 or later (no third-party runtime packages):

```sh
python3 scripts/profile.py build
python3 -m unittest discover -s tests -v
```

## Activity data

The workflow refreshes GitHub's default **contributions in the last year** calendar at approximately 04:17 UTC daily. GitHub may delay scheduled runs. The API chooses the same window as the native calendar, including its partial weeks; the script does not substitute a fixed 31-day or 365-day range. The heading uses `totalContributions` and verifies it equals the sum of every returned daily count. The line groups those days into Sunday-starting weeks without dropping or double-counting contributions.

Counts represent contributions, not only commits. The account's **Private contributions** setting must be enabled to include anonymous private contribution counts in the public chart using the built-in `GITHUB_TOKEN`. The owner has approved sharing these counts. Only dates and counts are requested and stored; private repository names and contents remain private. Turning this setting off will make future charts follow the smaller public total.

The workflow also runs on its initial publication, generator/workflow updates and manual dispatch. It uses the built-in token with `contents: write` to save the chart and its dated source data. Its updates are authored by `github-actions[bot]` and do not create artificial user contributions. No personal token, external chart host or separate deployment is required.

For a local live refresh, provide `GH_TOKEN` or `GITHUB_TOKEN` through the environment and run:

```sh
python3 scripts/profile.py refresh --username ozalpslan
```

Missing credentials, API errors, malformed responses, incomplete yearly date ranges and inconsistent totals fail the refresh before changing the existing charts. The last successful data and visible refresh timestamp remain available. Old 31-day caches are rejected rather than displayed under a yearly heading. Before the first successful fetch, the chart explicitly displays a pending state. The source is recorded in `assets/activity.json`.

GitHub disables scheduled workflows in public repositories after 60 days without repository activity. If refreshing stops, check the Actions tab, re-enable the workflow if necessary and run it manually. A failing run remains visible in Actions; the graph's date range exposes stale data.

## Publication

The local repository can be reviewed before publication. Publish only when the owner explicitly requests it. Confirm the remote is `https://github.com/ozalpslan/ozalpslan.git`; check for existing remote content before creating or updating the public repository. Do not overwrite an existing profile or change another repository's visibility.

After publication, check the first workflow run and inspect the profile in light and dark mode. Rolling back the README or header assets restores the earlier design. Disabling the activity workflow freezes the last chart.
