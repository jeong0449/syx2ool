# Background and Motivation

## From Floppy Disks to SysEx

The Korg X2 and X3 were introduced in the 1990s, when the 3.5-inch
floppy disk was still an ordinary way to move data between a synthesizer
and a computer. On workstations and synthesizers equipped with an
internal sequencer, the floppy drive was more than a convenient
accessory. It provided a practical means of saving and restoring songs,
sequences, sounds, and other user data.

Three decades later, the synthesizer itself may still work perfectly
well while its floppy disk drive does not. Even when the drive remains
operational, using floppy disks with a modern computer has become
increasingly inconvenient.

One solution is to replace the original floppy drive with a floppy
emulator such as a Gotek. This is probably the most straightforward way
to preserve the original disk-based workflow. However, I wanted to see
how far I could go **without replacing the floppy drive**.

Once the floppy disk route is removed, the MIDI ports become the most
important remaining connection between an X2/X3 and a modern computer.
Ordinary MIDI messages can be used for musical performance, while
**System Exclusive (SysEx)** messages provide access to data that is
specific to the synthesizer.

An old Java utility called **X3File2Sysex** was extremely valuable in
this respect. Together with old Korg disk files that I had fortunately
kept, it made it possible to convert disk-based data into SysEx form and
send it to the synthesizer.

This became particularly important when I replaced the X2's internal
backup battery. After the battery replacement, the **Factory Preload Data disk
had to be loaded to restore the factory data needed to make the
instrument properly usable again**. With a non-working floppy drive,
however, the normal disk-based restoration procedure was no longer
available. X3File2Sysex and a MIDI connection provided another route:
the necessary disk data could be converted to SysEx and transferred to
the X2 through MIDI.

That experience demonstrated that SysEx could effectively provide a
bridge around a failed floppy drive. But it also revealed the
limitations of the existing tools. Restoring prepared data was possible;
freely examining, modifying, converting, and reusing sequencer dumps was
another matter.

## Old Files That Became Valuable Again

I was also very fortunate to have found, many years ago, a ZIP archive
containing a collection of **Korg X2/X3 disk files** on a website that
is no longer easy to trace. At the time, keeping a copy of those files
did not seem particularly important. Decades later, however, they became
invaluable test material.

They contained real Songs, User Patterns, Programs, drum data, and other
examples of the data structures used by the X2/X3. Comparing these files
with SysEx dumps from an actual X2 made it possible to investigate the
format using real data rather than guesswork.

The **Korg X2/X3 Reference Guide** proved equally important. It contains
detailed information that is easy to overlook when using the instrument
simply as a synthesizer: SysEx commands, sequencer parameters, event
types, Pattern operations, MIDI behavior, and other technical details.

The manual did not by itself describe every byte of the dumped sequencer
data, but it provided the vocabulary and structural clues needed to
interpret what appeared in the actual SysEx files. The combination of
the Reference Guide, preserved disk files, X3File2Sysex, and dumps made
from real hardware became the foundation for reverse-engineering the
sequencer format.

## Why SyX2ool?

I could dump sequencer data from the X2 and send existing SysEx data
back to it, but I wanted to do more than treat a dump as an opaque block
of bytes.

I wanted to understand what was inside it: where the ten Songs and one
hundred User Patterns were stored, how tracks and events were
represented, and whether Standard MIDI Files could be converted to and
from the X2/X3 sequencer format.

Most of all, I wanted to make the **internal sequencer accessible from a
modern computer without depending on a floppy disk drive**.

That became the motivation for **SyX2ool**.

The name **SyX2ool** is a combination of **SysEx + X2 + Tool**. It began
as an experiment in decoding X2/X3 ALL SEQUENCE DATA dumps and gradually
grew into a command-line toolkit for importing and exporting Songs,
extracting User Patterns, analyzing SysEx data, and playing MIDI and
Pattern data back to the synthesizer in real time.

In that sense, SyX2ool is not intended to replace the X2/X3. Quite the
opposite: its purpose is to make more of the original instrument usable
again.

## Preserving More Than the Hardware

There is also a preservation aspect to this project. Old synthesizers
often survive longer than the information and software ecosystems that
once surrounded them. Personal websites disappear, download links break,
utilities become difficult to find, and knowledge once shared among
users gradually vanishes.

Some of the old files preserved on my own computer turned out, decades
later, to be invaluable references for understanding the X2/X3.

**The hardware survives, but sometimes the information disappears
first.**

SyX2ool is also an attempt to leave some of that information behind.
