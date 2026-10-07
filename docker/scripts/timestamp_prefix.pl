#!/usr/bin/env perl
# Prefixes each line from STDIN with a timestamp, for start.sh's log pipeline.
#
# This replaces an equivalent `awk '{ print strftime(...), $0; fflush() }'`
# one-liner. mawk (the awk providing /usr/bin/awk on this image) silently
# stalls reading from a live pipe here -- `canary | awk ...` produces zero
# output even though `canary | cat` and `canary | tee` both work fine on the
# exact same stream, and `stdbuf -i0` on awk doesn't help either. Whatever
# mawk's own input buffering is doing, it never unblocks on a quiet server,
# which is why logs/*.log sat empty for a full day during a real debugging
# session even on a normal, non-crashed server. Plain `perl -n` handles the
# same stream with no such stall.
use strict;
use warnings;
use POSIX qw(strftime);

$| = 1;
while (<STDIN>) {
	print strftime("%F %T - ", localtime), $_;
}
