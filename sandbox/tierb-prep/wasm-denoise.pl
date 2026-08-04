#!/usr/bin/perl
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Drop ONLY classified, known-benign wasm startup noise from a normalized stream,
# so the secondary oracle-vs-wasm diff is meaningful. Never drops test results.
# PRIMARY gate = exit code; this only cleans the SECONDARY stdout comparison.
#
# Benign = the web build's reduced stdlib / unimplemented-platform chatter:
#   - OIIO Sysutil::physical_memory unimplemented (one assert line)
#   - hashlib backend-missing ERROR lines
#   - Python Traceback blocks whose TERMINATING exception is a known-benign one
#     (unsupported hash type / _multiprocessing missing). A traceback ending in
#     any OTHER exception (e.g. AssertionError from a failing test) is KEPT.
use strict; use warnings;
my @benign = (
    qr/^ValueError: unsupported hash type\b/,
    qr/^ModuleNotFoundError: No module named '_multiprocessing'/,
);
my @buf; my $in_tb = 0;
sub flush_keep { print @buf; @buf = (); }
while (my $l = <STDIN>) {
    next if $l =~ /physical_memory: Assertion/;
    next if $l =~ /^ERROR:root:code for hash .* was not found\.$/;
    if (!$in_tb) {
        if ($l =~ /^Traceback \(most recent call last\):$/) { $in_tb = 1; @buf = ($l); next; }
        print $l; next;
    }
    # inside a traceback: indented frame lines accumulate; first non-indented,
    # non-blank line is the terminating exception.
    if ($l =~ /^\s/ || $l =~ /^\s*$/) { push @buf, $l; next; }
    # terminator line reached.
    my $benign = 0; for my $re (@benign) { if ($l =~ $re) { $benign = 1; last; } }
    if ($benign) { @buf = (); $in_tb = 0; next; }   # drop the whole benign block
    push @buf, $l; flush_keep(); $in_tb = 0;         # real traceback -> keep verbatim
}
flush_keep() if @buf;   # unterminated block at EOF -> keep
