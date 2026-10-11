# SyX2ool 0.1g 사용 메모

**SyX2ool --- Korg X2/X3 SysEx & MIDI Toolkit**

이 문서는 SyX2ool 0.1g의 기본 사용법과, 실제 Korg X2에서 확인한 사항,
현재 단계에서 의도적으로 구현하지 않은 기능을 간단히 정리한다.

## 기본 사용법

전체 도움말과 각 서브커맨드의 도움말은 다음과 같이 확인한다.

``` bash
python syx2ool.py -h
python syx2ool.py import -h
python syx2ool.py export -h
python syx2ool.py analyze -h
python syx2ool.py play -h
python syx2ool.py send -h
python syx2ool.py receive -h
python syx2ool.py ports
```

### SMF를 X2/X3 Song으로 가져오기

아무 Song 번호를 지정하지 않으면 기본 target은 **S9**이다.

``` bash
python syx2ool.py import Physical.mid Physical.syx
```

다른 Song을 지정하려면 `--song`을 사용한다.

``` bash
python syx2ool.py import song.mid out.syx --song 3
```

기존 ALL SEQUENCE DATA dump에서 특정 Song만 교체하려면 `--template`을
사용한다.

``` bash
python syx2ool.py import song.mid out.syx --song 3 --template old.syx
```

Song name을 직접 지정할 수도 있다.

``` bash
python syx2ool.py import song.mid out.syx --name MYSONG
```

### X2/X3 dump에서 Song 꺼내기

Song 하나:

``` bash
python syx2ool.py export dump.syx --song 9
```

여러 Song:

``` bash
python syx2ool.py export dump.syx --song 0,3,9
```

범위와 개별 번호를 섞어서 지정할 수도 있다.

``` bash
python syx2ool.py export dump.syx --song 0-3,7,9
```

실제 Sequence Data가 있는 모든 Song:

``` bash
python syx2ool.py export dump.syx --songs
```

Song export 결과는 기본적으로 SMF Format 1이며, X2/X3의 Track 구조를
가능한 한 유지한다.

### User Pattern 꺼내기

Pattern 하나 또는 여러 개:

``` bash
python syx2ool.py export dump.syx --pattern 20
python syx2ool.py export dump.syx --pattern 20,21,22
```

범위 지정:

``` bash
python syx2ool.py export dump.syx --pattern 0-19,30-35
```

데이터가 있는 모든 Pattern:

``` bash
python syx2ool.py export dump.syx --patterns
```

데이터가 있는 Song과 Pattern을 모두 꺼내려면:

``` bash
python syx2ool.py export dump.syx --all
```

Pattern을 MIDI로 꺼낼 때는 X2/X3의 note number를 그대로 보존한다. 특히
Drum Pattern은 PC의 GM drum map과 같은 소리가 난다고 보장하지 않는다.

### 0.1b--0.1c Pattern export 실기 검증

User Pattern의 event 해석은 실제 X2의 MIDI OUT과 비교하여 확인했다. P00을
X2의 `5A REAL-TIME PATTERN REC/EDIT`에서 재생하고 MIDI OUT을 PC에서
녹음한 뒤, SyX2ool이 P00에서 만든 SMF와 비교하였다.

P00에서 note number, Note On 시각, velocity와 note duration이 실제 X2의
출력과 거의 일치했다. 화면상 길어 보였던 일부 drum note도 변환 오류가
아니라 X2가 실제로 그 길이의 Note On/Off 간격으로 출력하는 것을 확인했다.
따라서 0.1b에서 정리한 Pattern note timing/length 해석은 0.1c에서도 그대로
유지한다.

Pattern 자체에는 Song Track의 MIDI channel 정보가 포함되어 있지 않다.
0.1b까지는 Pattern을 SMF로 export할 때 편의상 **MIDI CH10**을 사용했으나,
실제 X2에서 Track 1을 `CH1G`로 두고 P00을 preview했을 때 MIDI OUT의 note
message가 모두 **CH1**으로 출력되는 것을 확인했다. 이에 따라 0.1c에서는
Pattern export의 기본 channel을 **CH1**로 변경하였다.

``` text
SyX2ool 0.1b : Pattern export -> CH10
SyX2ool 0.1c : Pattern export -> CH1
```

이 변경은 Pattern의 note number, timing, velocity 또는 duration을 바꾸는
것이 아니다. Pattern을 어느 Track에서 사용할지는 X2의 Track/Program
context에 의해 결정되므로, CH1은 Pattern 자체의 고유 channel이라는 뜻이
아니라 SMF로 꺼낼 때 사용하는 현재의 기본값이다.

또한 현재 Pattern SMF에는 tempo를 **120 BPM**으로 기록한다. User Pattern
자체만으로는 그것을 재생하던 Song의 tempo context를 알 수 없기 때문이다.
따라서 X2에 다시 MIDI로 보내어 원래 연주를 재현하려면 실제 Song/Pattern에서
사용하던 tempo를 별도로 맞추어야 한다.

### MIDI OUT port 확인: `ports`

0.1f부터 재생 전에 설치되어 있는 MIDI port를 독립적으로 확인할 수 있도록
`ports` 서브커맨드를 추가했다.

``` bash
python syx2ool.py ports
```

출력 예시는 다음과 같다.

``` text
MIDI OUT ports
--------------
0: Mackie Onyx Producer 2-2 ...
```

표시된 MIDI OUT 번호 또는 고유한 이름 일부를 `play --out-port`에 사용할 수 있다.
0.1g에서는 `play`, `send`, `receive`의 방향 표기를 일관되게 하기 위해
`--out-port`와 `--in-port`를 정식 옵션명으로 사용한다. 기존 `play --port`도
호환 alias로 남겨 두었으며, `play --list-ports`도 계속 사용할 수 있다.

### MIDI 재생: `play`

0.1f에서는 MIDI OUT으로 SMF 또는 X2/X3 User Pattern을 직접 재생하는
`play` 서브커맨드를 추가했다. MIDI 출력에는 `mido`와 `python-rtmidi`가
필요하다.

``` bash
py -m pip install mido python-rtmidi
```

사용 가능한 MIDI OUT port를 먼저 확인한다.

``` bash
python syx2ool.py play --list-ports
```

일반 SMF를 재생하려면 MIDI 파일과 출력 port를 지정한다.

``` bash
python syx2ool.py play song.mid --out-port 0
```

기본적으로 SMF에 기록된 tempo와 MIDI channel을 그대로 사용한다. 따라서
GM MIDI 파일을 재생할 때는 보통 `--channel`을 지정하지 않는다.

Pattern처럼 일정한 tempo로 반복 재생하려면 다음과 같이 사용할 수 있다.

``` bash
python syx2ool.py play P00.mid --out-port 0 --loop
python syx2ool.py play P00.mid --out-port 0 --bpm 116 --loop
```

`--bpm`을 지정하면 파일에 들어 있는 tempo 대신 지정한 BPM으로 재생한다.
`--channel`을 지정하면 channel message를 해당 MIDI channel로 강제
remap한다. 사용자에게 보이는 channel 번호는 1--16이다.

``` bash
python syx2ool.py play P00.mid --out-port 0 --channel 1 --bpm 116 --loop
```

이 기능은 Pattern SMF의 기본 channel이 무엇이든 실제 연주 시점에 원하는
X2/X3 Sequencer Track의 channel에 맞출 수 있게 하기 위한 것이다.

0.1f에서는 ALL SEQUENCE DATA SysEx에서 User Pattern을 직접 꺼내 MIDI
OUT으로 보낼 수도 있다. 중간 `.mid` 파일을 만들 필요가 없다.

``` bash
python syx2ool.py play X3DRUMS.syx --pattern 0 --out-port 0 --bpm 116 --loop
```

개념적으로는 다음과 같다.

``` text
X2/X3 ALL SEQUENCE DATA SysEx
        |
        | --pattern Pxx
        v
SyX2ool Pattern decoder
        |
        v
MIDI OUT
        |
        v
Korg X2/X3
```

Pattern을 직접 재생할 때도 note number를 GM drum map으로 자동 변환하지
않는다. X2/X3 Pattern의 원래 note number를 보존하는 원칙은 export와 같다.

반복 재생은 `--loop`로 지정하고 `Ctrl+C`로 중단한다. 재생 종료 시에는
남아 있는 note가 계속 울리는 것을 줄이기 위해 MIDI panic 처리를 한다.

### 0.1f의 Pattern loop 및 timing 수정

0.1f에서 `play --loop`의 반복 경계를 다시 정리했다. 핵심 원칙은 **마지막
MIDI event의 시각을 Pattern의 끝으로 간주하지 않는 것**이다. 드럼 Pattern은
마지막 Note Off 뒤에 쉼표가 남아 있을 수 있으므로, 마지막 event 직후에 다음
loop를 시작하면 반복할수록 박자가 당겨져 들린다.

실제 P00 시험에서는 마지막 event가 746 tick에 있었지만, 96 PPQN, 4/4의
2마디 길이는 768 tick이다. 따라서 0.1f는 time signature와 PPQN으로
`ticks per bar`를 계산하고, 마지막 event 위치를 **다음 완전한 마디 경계까지
올림**하여 loop 길이를 정한다.

``` text
P00: last event = 746 ticks
4/4, 96 PPQN: 1 bar = 384 ticks
ceil(746 / 384) × 384 = 768 ticks = 2 bars
```

같은 원리로 1-bar Pattern에서 마지막 event가 384 tick보다 앞에서 끝나면
loop 길이는 384 tick으로 잡힌다. 따라서 X3DRUMS처럼 1-bar와 2-bar Pattern이
섞여 있어도 별도의 길이 지정 없이 처리할 수 있다.

재생 scheduler도 이전 event에서 상대적으로 sleep을 이어 붙이는 방식이 아니라
`time.perf_counter()`의 **절대 시각**을 기준으로 한다. N번째 loop의 시작은
항상 최초 origin으로부터 계산하므로 앞 회차의 작은 지연이 다음 회차에
누적되지 않는다.

P00을 116 BPM으로 실제 시험했을 때 다음과 같이 확인되었다.

``` text
duration=4.137928 s
last_tick=746
loop_ticks=768
bars=2
time=4/4
beats=8
```

각 loop 시작 오차는 약 +0.3~+0.5 ms 수준이었다. 116 BPM에서 8 beat의
이론적 길이는 약 4.137931초이므로 실용적으로 일치한다.

필요하면 `--timing-log`로 scheduler의 계산값과 실제 loop 시작 오차를
확인할 수 있다.

``` bash
python syx2ool.py play P00.mid --out-port 0 --bpm 116 --loop --timing-log
```

`--bpm`을 생략한 경우에는 SMF의 tempo map을 사용하여 계산된 마디 경계까지의
시간을 구한다. `--bpm`을 지정하면 지정 BPM이 loop 전체에 적용된다.


### SysEx 송신과 수신: `send`, `receive`

0.1g에서는 X2/X3와 SysEx dump를 직접 주고받는 `send`와 `receive`
서브커맨드를 추가했다.

PC에서 X2/X3로 SysEx를 보내려면 MIDI OUT을 지정한다. X2/X3의 완료 응답까지
확인하려면 MIDI IN도 함께 지정한다.

``` bash
python syx2ool.py send dump.syx --out-port 1 --in-port 0
```

X2/X3의 Function에 따라 SyX2ool은 ACK/NAK 또는 WRITE COMPLETED/WRITE ERROR
등의 완료 응답을 구분한다. 하나의 큰 SysEx message를 임의로 잘라서 보내지
않으며, 여러 개의 완전한 SysEx message가 파일에 들어 있을 때만 message 사이에
delay를 둔다.

X2/X3에서 PC로 SysEx를 받으려면 다음과 같이 사용한다.

``` bash
python syx2ool.py receive dump.syx --in-port 0 --count 1
```

`receive`의 출력 파일은 full path를 쓸 필요가 없다. 위와 같이 상대 경로 또는
파일명만 쓰면 현재 작업 directory를 기준으로 저장된다.

Windows에서는 `python-rtmidi`의 일반 입력 경로 대신 native WinMM long-data
buffer를 직접 사용한다. 긴 SysEx가 입력 backend의 고정 buffer 크기 때문에
유실되는 문제를 피하기 위한 것이다. 현재 구현은 4,096-byte buffer 16개를
순환시키면서 들어오는 조각을 다시 하나의 `F0 ... F7` SysEx message로 조립한다.

수신 중에는 실제로 받은 byte 수가 표시된다.

``` text
RX 220,903 bytes
Received SysEx 1: 220,903 bytes  X2/X3 50H ALL DATA DUMP
```

송신 중 TX progress는 MIDI backend가 실제 전송 완료 byte 수를 중간에 알려 주지
않으므로 물리적 MIDI 전송 속도를 바탕으로 한 **추정값**이다. 화면의 `~` 표시는
추정값이라는 뜻이며, `send()`가 끝났을 때 표시되는 100%만 실제 완료를 의미한다.

### 0.1g 대용량 SysEx 실기 검증

0.1g의 `send`와 `receive`는 실제 Korg X2와 Mackie Onyx Producer 2•2 MIDI
interface를 사용하여 **Windows에서** 시험했다.

먼저 약 37 KB의 `4CH ALL PROGRAM PARAMETER DUMP`를 정상적으로 수신했다.
이어 X2의 `50H ALL DATA DUMP`를 수신했으며, 하나의 SysEx message 크기는
**220,903 bytes**였다. 이 파일은 `F0`에서 시작하여 `F7`로 정상 종료되었고,
SyX2ool은 여러 WinMM long-data buffer에 나뉘어 들어온 데이터를 하나의 SysEx로
재조립하여 저장했다.

그 다음 방금 받은 220,903-byte ALL DATA DUMP 파일을 수정하지 않고 X2로 다시
전송했다. 전송에는 약 76초가 걸렸으며, X2는 처리가 끝난 뒤 다음과 같이
`23H ACK`를 반환했다.

``` text
Sending 1/1: 220903 bytes  X2/X3 50H ALL DATA DUMP
MIDI send call completed in 76.367 s
X2/X3: ACK (23H) — data load/processing completed
```

따라서 다음 왕복 경로는 실제 장비에서 확인되었다.

``` text
Korg X2
   |
   |  50H ALL DATA DUMP
   v
SyX2ool receive
   |
   |  220,903-byte .syx file
   v
SyX2ool send
   |
   |  same SysEx message
   v
Korg X2
   |
   +--> 23H ACK
```

이 결과는 **Windows + Mackie Onyx Producer 2•2 + Korg X2** 조합에서 확인한
것이다. SyX2ool의 일반 MIDI 기능은 Mido와 python-rtmidi를 사용하며 다른
platform에서도 동작하도록 작성되어 있지만, Linux나 macOS에서 이와 같은
대용량 SysEx 송수신을 실제 X2/X3 하드웨어로 검증하지는 않았다. 따라서 현재
단계에서는 Windows에서의 실기 검증 결과와 다른 platform의 코드상 지원 가능성을
구분해서 기록하는 것이 정확하다.

### dump 구조 조사

파일을 변환하지 않고 Song, Track, Pattern의 사용 상태와 address 등을
살펴보려면:

``` bash
python syx2ool.py analyze dump.syx
```

`analyze`는 S0--S9의 Song name, tempo, 데이터가 있는 Track, Sequence
address와 P00--P99의 사용 여부 등을 확인하는 용도이다.

## 실기 확인 사항: Next Song

SMF를 Song으로 import할 때 target Song의 `Next Song`은 **OFF**로
설정한다.

초기 구현에서는 실제 X2의 S9에서 얻은 GM Song Control Data 296 bytes를
`GM_S9_CONTROL`이라는 이름으로 두고 target Song에 그대로 복사했다.
그런데 이 캡처에는 GM 초기화와 직접 관계없는 `Next Song No. = 0`도
포함되어 있었다. 이 값을 S0에 그대로 복사하면 `S0 → S0`이라는 자기
참조가 된다.

실기 시험에서는 Physical을 S0에 넣었을 때 이 상태에서 정상 재생되지
않았으며, Song Control Data의 `Next Song No.` 한 바이트만 `0x00`에서
`0xFF` (**OFF**)로 바꾸자 정상 재생되었다. 같은 방식으로 S1에 넣은
Physical도 정상 재생되는 것을 확인했다.

따라서 현재 버전에서는 import할 때 다음 원칙을 적용한다.

``` text
target Song의 Next Song No. = 0xFF  (OFF)
```

이 설정은 Song chain을 임의로 만들지 않는다는 의미이기도 하다. 사용자가
의도적으로 Song을 연속 재생하도록 연결하는 기능은 현재 import의 대상이
아니다.

이번 시험으로 함께 확인된 사항은 다음과 같다.

-   Physical의 Sequence Data와 Song address relocation 자체에는 문제가
    없었다.
-   S0뿐 아니라 S1에도 같은 Physical 데이터를 넣어 정상 재생할 수
    있었다.
-   `2G Erase Song`은 Sequence Data를 지우지만, Copy from
    Combination으로 들어간 Track Setting이나 Song Name까지 `New Song`
    상태로 초기화하지는 않는다.
-   따라서 SyX2ool에서 `no sequence data`와 완전히 초기화된 `New Song`은
    서로 다른 상태로 취급하는 것이 정확하다.

### GM Song Control template

S0과 S1에 Physical을 실제로 넣어 연주한 시험을 통해, 이 296-byte Control
Data는 S9에만 한정된 설정이 아니라 target Song을 GM 연주용 상태로 만드는
template로 사용할 수 있음을 확인했다. 따라서 코드의 변수명도 역할에 맞게

``` python
GM_S9_CONTROL
```

에서

``` python
GM_SONG_CONTROL
```

로 변경했다.

이 변경은 **변수명만 정리한 것**이며 파일 형식이나 import 동작을 바꾸는
것은 아니다. `--song 0`, `--song 1`처럼 다른 Song을 지정해도 SyX2ool이
해당 Song의 Control Data를 이 GM Song template로 설정하므로, X2에서
사용자가 미리 `8F GM Song Mode`를 실행할 필요는 없다. Import 후에는
tempo와 Song name을 입력 MIDI에 맞게 설정하고, `Next Song No.`는
`0xFF`(OFF)로 명시적으로 보정한다.

## 0.1g에서도 의도적으로 아직 넣지 않은 기능

SyX2ool 0.1g는 먼저 실제 X2/X3에서 확인된 데이터 구조와 변환 동작을
안정적으로 다루는 것을 목표로 한다. 다음 기능은 불완전한 추정으로
구현하지 않고 후속 버전으로 남겨 둔다.

-   **Pattern Put의 Song export 시 자동 전개(flatten)**\
    Song Track에 `Put Pxx`가 들어 있을 때 해당 User Pattern의 event를
    Song timeline에 펼치는 기능은 아직 구현하지 않았다. Pattern Put의
    binary 구조를 실제 dump로 충분히 확인한 뒤 추가한다.

-   **X2/X3 Drum Kit → GM Drum Map 자동 변환**\
    User Pattern의 note number는 그대로 보존한다. X2/X3의 Drum Kit
    assignment를 충분히 해독하기 전에는 킥, 스네어, 퍼커션 등을 추정하여
    GM note로 바꾸지 않는다.

-   **Combi-derived Song의 다중 Track 재현**\
    Combi를 Sequencer로 복사한 Song에서는 실제 note sequence가 한
    Track에만 있고 같은 MIDI channel을 가진 여러 Track이 동시에 발음할
    수 있다. Export할 때 이를 임의로 여러 SMF Track에 복제하지 않는다.
    실제로 기록된 Sequence Event의 보존을 우선한다.

-   **SMF Format 1 import**\
    현재 import의 출발점은 실기에서 검증한 Format 0 변환기이다. Format
    1의 여러 Track을 X2/X3 Track으로 가져오는 기능은 후속 과제로 둔다.

-   **Tempo change와 time-signature change import**\
    현재 import는 96 PPQN, constant 4/4, 하나의 일정한 tempo를 기본
    조건으로 한다. X2/X3 Tempo Track을 이용한 변화 처리까지는 아직
    확장하지 않았다.

-   **검증되지 않은 event의 임의 변환**\
    해석하지 못한 X2/X3 event를 적당히 MIDI event로 추정하거나 조용히
    버리지 않는다. 가능한 경우 경고를 내고, 정확한 구조를 확인한 뒤
    지원한다.

-   **X2/X3 Program의 GM Program 자동 치환**\
    X2/X3 고유 Program을 비슷해 보이는 GM Program으로 임의 변환하지
    않는다. SyX2ool의 기본 원칙은 음색의 추정보다 원래 데이터의
    보존이다.

-   **byte-for-byte SMF round-trip**\
    SMF에는 X2/X3에서 보존할 수 없는 meta event가 있고, X2/X3에서는
    velocity 양자화도 일어난다. 따라서 원본 MIDI와 복원 MIDI의 파일
    자체가 완전히 같아지는 것을 목표로 하지 않는다. Note timing,
    channel, pitch, controller, Program Change 등 실제 연주에 필요한
    musical event의 일치를 우선한다.

## 현재의 방향

0.1g는 파일 변환과 MIDI 재생에 더해 실제 X2/X3와의 SysEx 송수신까지 포함하는
기본 골격을 갖추었다.

``` text
SMF
  ⇅
SyX2ool
  ⇅
X2/X3 SysEx dump
  ⇅
MIDI IN / MIDI OUT
  ⇅
X2/X3
```

앞으로 Pattern과 Pattern Put의 실제 구조를 검증하고, SMF Format 1과
Tempo Track 지원을 확대하면서 X2/X3 내부 Sequencer와 PC 사이에서
데이터를 가능한 한 손실 없이 이동시키는 도구로 발전시키는 것을 목표로
한다.
