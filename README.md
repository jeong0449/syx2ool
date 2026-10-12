# SyX2ool

**SyX2ool** is a command-line SysEx and MIDI toolkit for the **Korg
X2/X3** synthesizers.

The name **SyX2ool** is a combination of **SysEx + X2 + Tool**. The
project grew out of experiments with Korg X2/X3 sequencer dumps,
Standard MIDI Files (SMF), drum patterns, and real-time MIDI playback.

SyX2ool is particularly useful for an X2/X3 whose floppy disk drive is
no longer usable. In such a situation, transferring data over a MIDI
connection using SysEx can provide a practical way to move sequencer
data between the synthesizer and a modern computer without relying on
floppy disks.

> This is an experimental, unofficial project and is not affiliated with
> Korg. Historical Korg X2/X3 disk files used during the development of
> this project are not included in this repository. If you are researching
> these legacy formats, please contact the author.

## Features

- Import an SMF into X2/X3 Song SysEx data (S9)
- Export X2/X3 Songs from ALL SEQUENCE DATA SysEx as SMF
- Export X2/X3 User Patterns from ALL SEQUENCE DATA SysEx as SMF
- Analyze X2/X3 sequencer SysEx data
- Play SMF files through a MIDI OUT port
- Play X2/X3 User Patterns directly from ALL SEQUENCE DATA SysEx
- Loop X2/X3 User Patterns on musical bar boundaries
- List available MIDI input and output ports
- Send X2/X3 SysEx files and monitor ACK/NAK responses
- Receive and save large X2/X3 SysEx transfers

Some parts of the proprietary X2/X3 sequencer format were determined
experimentally and may not yet be completely understood.

## Requirements

-   Python 3
-   `mido`
-   `python-rtmidi`

``` bash
pip install mido python-rtmidi
```

## Usage examples

Show help:

``` bash
python syx2ool.py -h
python syx2ool.py export -h
python syx2ool.py import -h
python syx2ool.py play -h
```

List MIDI ports:

``` bash
python syx2ool.py ports
```

Analyze an X2/X3 SysEx dump:

``` bash
python syx2ool.py analyze Song.syx
```

Export Song 9:

``` bash
python syx2ool.py export Song.syx --song 9
```

Export several Songs or ranges:

``` bash
python syx2ool.py export Song.syx --song 0,3,9
python syx2ool.py export Song.syx --song 0-3,7,9
```

Export Pattern P00 or a range of Patterns:

``` bash
python syx2ool.py export X3DRUMS.syx --pattern 0
python syx2ool.py export X3DRUMS.syx --pattern 0-19
```

A Pattern itself does not contain a complete Song/Track MIDI-channel
context. syx2ool therefore does not assume that a Pattern must use GM
drum channel 10.

Import an SMF into an X2/X3 Song:

``` bash
python syx2ool.py import Physical.mid Physical.syx
python syx2ool.py import Physical.mid Physical.syx --song 0
```

Play an ordinary MIDI file:

``` bash
python syx2ool.py play MySong.mid --port 0
```

Override the tempo or force a playback channel:

``` bash
python syx2ool.py play P00.mid --port 0 --bpm 116
python syx2ool.py play P00.mid --port 0 --bpm 116 --channel 1
```

Loop a Pattern:

``` bash
python syx2ool.py play P00.mid --port 0 --bpm 116 --loop
```

Pattern looping is aligned to **musical bar boundaries**, rather than
simply restarting after the last MIDI event. For example, a two-bar 4/4
Pattern at 96 PPQN occupies 768 ticks even if its last event occurs at
tick 746. syx2ool preserves the remaining silence and starts the next
loop at tick 768.

Timing diagnostics are available with:

``` bash
python syx2ool.py play P00.mid --port 0 --bpm 116 --loop --timing-log
```

A Pattern can also be decoded and played directly from an ALL SEQUENCE
DATA SysEx dump:

``` bash
python syx2ool.py play X3DRUMS.syx --pattern 0 --port 0 --bpm 116 --channel 1 --loop
```

This allows the PC to act as a Pattern player while the X2/X3 serves as
the sound generator.

## About the X2/X3 format

Korg X2/X3 sequencer data uses a proprietary representation inside
SysEx. syx2ool includes code for structures investigated and tested
during development, including Korg SysEx packing, sequencer control and
sequence areas, Song and Pattern address information, and native
sequencer events.

The longer-term goal is not merely file conversion, but to make X2/X3
sequencer and Pattern resources easier to use from a modern computer,
including real-time Pattern performance and arrangement.

## Status

SyX2ool is experimental software. Keep backups of original SysEx and
SNG data and test generated data carefully.

Hardware testing has been performed with a Korg X2 connected through
a Mackie Onyx Producer 2•2 MIDI interface on Windows. In testing,
SyX2ool successfully received a single 220,903-byte ALL DATA DUMP
(50H) from the X2, saved it to a file, transmitted the same dump back
to the synthesizer, and received an ACK (23H) confirming successful
processing.

Large SysEx transfer has therefore been verified on Windows with this
hardware configuration. The program is designed to use Mido and
python-rtmidi on other platforms as well, but large SysEx transfer has
not yet been verified with actual X2/X3 hardware on Linux or macOS.

## License

syx2ool is released under the **MIT License**. See the `LICENSE` file for details.
