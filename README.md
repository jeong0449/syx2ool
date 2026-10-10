# SyX2tool

**SyX2tool** is a command-line SysEx and MIDI toolkit for the **Korg
X2/X3** synthesizers.

The name **SyX2tool** is a combination of **SysEx + X2 + Tool**. The
project grew out of experiments with Korg X2/X3 sequencer dumps,
Standard MIDI Files (SMF), drum patterns, and real-time MIDI playback.

> This is an experimental, unofficial project and is not affiliated with
> Korg.

## Features

-   Import an SMF into an X2/X3 Song
-   Export Songs from an ALL SEQUENCE DATA SysEx dump as SMF
-   Export X2/X3 User Patterns as SMF
-   Analyze X2/X3 sequencer SysEx data
-   Play ordinary MIDI files through a MIDI OUT port
-   Play X2/X3 Patterns directly from a SysEx dump
-   Loop Patterns on musical bar boundaries
-   List available MIDI ports

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
python syx2tool.py -h
python syx2tool.py export -h
python syx2tool.py import -h
python syx2tool.py play -h
```

List MIDI ports:

``` bash
python syx2tool.py ports
```

Analyze an X2/X3 SysEx dump:

``` bash
python syx2tool.py analyze Song.syx
```

Export Song 9:

``` bash
python syx2tool.py export Song.syx --song 9
```

Export several Songs or ranges:

``` bash
python syx2tool.py export Song.syx --song 0,3,9
python syx2tool.py export Song.syx --song 0-3,7,9
```

Export Pattern P00 or a range of Patterns:

``` bash
python syx2tool.py export X3DRUMS.syx --pattern 0
python syx2tool.py export X3DRUMS.syx --pattern 0-19
```

A Pattern itself does not contain a complete Song/Track MIDI-channel
context. SyX2tool therefore does not assume that a Pattern must use GM
drum channel 10.

Import an SMF into an X2/X3 Song:

``` bash
python syx2tool.py import Physical.mid Physical.syx
python syx2tool.py import Physical.mid Physical.syx --song 0
```

Play an ordinary MIDI file:

``` bash
python syx2tool.py play MySong.mid --port 0
```

Override the tempo or force a playback channel:

``` bash
python syx2tool.py play P00.mid --port 0 --bpm 116
python syx2tool.py play P00.mid --port 0 --bpm 116 --channel 1
```

Loop a Pattern:

``` bash
python syx2tool.py play P00.mid --port 0 --bpm 116 --loop
```

Pattern looping is aligned to **musical bar boundaries**, rather than
simply restarting after the last MIDI event. For example, a two-bar 4/4
Pattern at 96 PPQN occupies 768 ticks even if its last event occurs at
tick 746. SyX2tool preserves the remaining silence and starts the next
loop at tick 768.

Timing diagnostics are available with:

``` bash
python syx2tool.py play P00.mid --port 0 --bpm 116 --loop --timing-log
```

A Pattern can also be decoded and played directly from an ALL SEQUENCE
DATA SysEx dump:

``` bash
python syx2tool.py play X3DRUMS.syx --pattern 0 --port 0 --bpm 116 --channel 1 --loop
```

This allows the PC to act as a Pattern player while the X2/X3 serves as
the sound generator.

## About the X2/X3 format

Korg X2/X3 sequencer data uses a proprietary representation inside
SysEx. SyX2tool includes code for structures investigated and tested
during development, including Korg SysEx packing, sequencer control and
sequence areas, Song and Pattern address information, and native
sequencer events.

The longer-term goal is not merely file conversion, but to make X2/X3
sequencer and Pattern resources easier to use from a modern computer,
including real-time Pattern performance and arrangement.

## Status

SyX2tool is experimental software. Keep backups of original SysEx and
SNG data and test generated data carefully. Hardware testing to date has
primarily been performed with a Korg X2.

## License

A license has not yet been specified. Add a `LICENSE` file before
defining redistribution or contribution terms.
