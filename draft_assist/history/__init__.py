"""The match history analyser: what correlates with winning, for one account.

It was a separate single-file browser tool (`DotaGameHistoryAnalyser`) and
is now part of this app, at the user's request. Nothing about the draft
depends on it and it depends on nothing about the draft: it reads a
player's public match history from OpenDota, buckets it, and reports which
buckets sit far enough off that player's own win rate to be worth a second
look.

THE QUESTION IS INSTRUMENTATION, NOT COACHING. The player's own win rate
across the filtered sample is the datum, and every analysis asks whether a
bucket is distinguishable from sampling noise against it. Nothing here
knows anything about how to play Dota, and it must never pretend to: a
finding is a hypothesis to test against the next hundred games.
"""
