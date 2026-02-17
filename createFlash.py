"""
Build `syllables.json`, an index mapping every pinyin syllable to the
tone-perfect assets (audio + metadata) for tones 1–4 and speakers
FV1/FV2/FV3/MV1/MV2/MV3.

Structure:
{
  "ma": {
    "1": { "FV1": { audio, custom_xml, dc_xml, meta }, "FV2": null, ... },
    "2": { ... },
    "3": { ... },
    "4": { ... }
  },
  ...
}

Missing slots are set to null. A summary is printed showing coverage and
which syllable/tone/speaker combos are missing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent
AUDIO_DIR = ROOT / "tone_perfect"
XML_DIR = ROOT / "tone_perfect-2"
OUTPUT_PATH = ROOT / "syllables.json"

SPEAKERS = ["FV1", "FV2", "FV3", "MV1", "MV2", "MV3"]
TONES = ["1", "2", "3", "4"]

# Raw syllable list copied from user (with headings). We'll normalize it.
RAW_SYLLABLES = """
A
a
ai
an
ang
ao
B
ba
bai
ban
bang
bao
bei
ben
beng
bi
bian
biao
bie
bin
bing
bo
bu
C
ca
cai
can
cang
cao
ce
cen
ceng
ci
cong
cou
cu
cuan
cui
cun
cuo
CH
cha
chai
chan
chang
chao
che
chen
cheng
chi
chong
chou
chu
chua
chuai
chuan
chuang
chui
chun
chuo
D
da
dai
dan
dang
dao
de
deng
di
dia
dian
diao
die
ding
diu
dong
dou
du
duan
dui
dun
duo
E
e
ei
en
eng
er
F
fa
fan
fang
fei
fen
feng
fo
fou
fu
G
ga
gai
gan
gang
gao
ge
gei
gen
geng
gong
gou
gu
gua
guai
guan
guang
gui
gun
guo
H
ha
hai
han
hang
hao
he
hei
hen
heng
hong
hou
hu
hua
huai
huan
huang
hui
hun
huo
J
ji
jia
jian
jiang
jiao
jie
jin
jing
jiong
jiu
ju
juan
jue
jun
K
ka
kai
kan
kang
kao
ke
ken
keng
kong
kou
ku
kua
kuai
kuan
kuang
kui
kun
kuo
L
la
lai
lan
lang
lao
le
lei
leng
li
lia
lian
liang
liao
lie
lin
ling
liu
long
lou
lu
luan
lun
luo
lü
lüe
M
ma
mai
man
mang
mao
me
mei
men
meng
mi
mian
miao
mie
min
ming
miu
mo
mou
mu
N
na
nai
nan
nang
nao
ne
nei
nen
neng
ni
nian
niang
niao
nie
nin
ning
niu
nong
nu
nuan
nun
nuo
nü
nüe
O
o
ou
P
pa
pai
pan
pang
pao
pei
pen
peng
pi
pian
piao
pie
pin
ping
po
pou
pu
Q
qi
qia
qian
qiang
qiao
qie
qin
qing
qiong
qiu
qu
quan
que
qun
R
ran
rang
rao
re
ren
reng
ri
rong
rou
ru
ruan
rui
run
ruo
S
sa
sai
san
sang
sao
se
sen
seng
si
song
sou
su
suan
sui
sun
suo
SH
sha
shai
shan
shang
shao
she
shei
shen
sheng
shi
shou
shu
shua
shuai
shuan
shuang
shui
shun
shuo
T
ta
tai
tan
tang
tao
te
teng
ti
tian
tiao
tie
ting
tong
tou
tu
tuan
tui
tun
tuo
W
wa
wai
wan
wang
wei
wen
weng
wo
wu
X
xi
xia
xian
xiang
xiao
xie
xin
xing
xiong
xiu
xu
xuan
xue
xun
Y
ya
yan
yang
yao
ye
yi
yin
ying
yo
yong
you
yu
yuan
yue
yun
Z
za
zai
zan
zang
zao
ze
zei
zen
zeng
zi
zong
zou
zu
zuan
zui
zun
zuo
ZH
zha
zhai
zhan
zhang
zhao
zhe
zhei
zhen
zheng
zhi
zhong
zhou
zhu
zhua
zhuai
zhuan
zhuang
zhui
zhun
zhuo
"""


def _normalize_syllable(line: str) -> Optional[str]:
    # Drop headings (single uppercase letter or digraph labels).
    if line.isupper():
        return None
    line = re.sub(r"\s*\(.*?\)", "", line)  # strip parentheses content (and preceding space)
    line = line.strip()
    if not line:
        return None
    # Convert ü to v to match Tone Perfect filenames.
    line = line.replace("ü", "v").replace("Ü", "v")
    line = line.lower()
    # Keep only letters
    line = re.sub(r"[^a-z]", "", line)
    return line or None


def load_syllable_list(raw: str = RAW_SYLLABLES) -> List[str]:
    out: List[str] = []
    for line in raw.splitlines():
        norm = _normalize_syllable(line)
        if norm and norm not in out:
            out.append(norm)
    return out


SYLLABLES = load_syllable_list()


@dataclass
class AudioMeta:
    audio: str
    custom_xml: Optional[str]
    dc_xml: Optional[str]
    meta: Dict


def parse_audio_filename(path: Path) -> Tuple[str, str, str]:
    """
    Returns (syllable, tone, speaker) from <syllable><tone>_<speaker>_MP3.mp3.
    """
    m = re.match(r"(.+?)([1-4])_([A-Za-z]{2}\d)_MP3\.mp3$", path.name)
    if not m:
        raise ValueError(f"Unrecognized audio filename: {path.name}")
    syllable, tone, speaker = m.groups()
    return syllable, tone, speaker


def split_initial_final(syllable: str) -> Tuple[str, str]:
    initials = [
        "zh",
        "ch",
        "sh",
        "b",
        "p",
        "m",
        "f",
        "d",
        "t",
        "n",
        "l",
        "g",
        "k",
        "h",
        "j",
        "q",
        "x",
        "r",
        "z",
        "c",
        "s",
        "y",
        "w",
    ]
    for init in initials:
        if syllable.startswith(init):
            return init, syllable[len(init) :]
    return "", syllable


def read_custom(identifier: str) -> Tuple[Optional[str], Dict]:
    """
    Returns (path, meta_dict).
    """
    path = XML_DIR / f"{identifier}_CUSTOM.xml"
    if not path.exists():
        return None, {}
    root = ET.parse(path).getroot()
    meta: Dict = {child.tag: child.text or "" for child in root}
    # collect repeated character_forms
    meta["character_forms"] = [el.text or "" for el in root.findall("character_forms")]
    characters = []
    for el in root.findall("character"):
        characters.append(
            {
                "simplified": el.findtext("simplified", default=""),
                "traditional": el.findtext("traditional", default=""),
            }
        )
    meta["characters"] = characters
    return str(path.relative_to(ROOT)), meta


def read_dc(identifier: str) -> Optional[str]:
    path = XML_DIR / f"{identifier}_DC.xml"
    return str(path.relative_to(ROOT)) if path.exists() else None


def build_index() -> Tuple[Dict[str, Dict[str, Dict[str, Optional[Dict]]]], List[str]]:
    # Initialize all slots to None
    index: Dict[str, Dict[str, Dict[str, Optional[Dict]]]] = {
        syll: {tone: {sp: None for sp in SPEAKERS} for tone in TONES} for syll in SYLLABLES
    }

    unknown_files: List[str] = []

    for audio_file in AUDIO_DIR.glob("*.mp3"):
        try:
            syllable, tone, speaker = parse_audio_filename(audio_file)
        except ValueError:
            unknown_files.append(audio_file.name)
            continue

        # Skip syllables not in the provided list but record them
        if syllable not in index:
            unknown_files.append(audio_file.name)
            continue

        identifier = f"{syllable}{tone}_{speaker}"
        custom_path, meta = read_custom(identifier)
        dc_path = read_dc(identifier)

        if not meta:
            # minimal meta fallback
            initial, final = split_initial_final(syllable)
            meta = {
                "sound": syllable,
                "tone": int(tone),
                "pinyin": None,
                "initial": initial or "Null",
                "final": final,
                "speaker": speaker,
                "identifier": identifier,
            }

        entry = {
            "audio": str(audio_file.relative_to(ROOT)),
            "custom_xml": custom_path,
            "dc_xml": dc_path,
            "meta": meta,
        }
        index[syllable][tone][speaker] = entry

    return index, unknown_files


def summarize(
    index: Dict[str, Dict[str, Dict[str, Optional[Dict]]]], unknown_files: List[str]
) -> None:
    total_slots = len(SYLLABLES) * len(TONES) * len(SPEAKERS)
    filled = sum(1 for s in index.values() for t in s.values() for v in t.values() if v is not None)
    missing = total_slots - filled
    print(f"Total slots: {total_slots}, filled: {filled}, missing: {missing}")

    missing_details = []
    for syllable, tones in index.items():
        for tone, speakers in tones.items():
            missing_sp = [sp for sp, val in speakers.items() if val is None]
            if missing_sp:
                missing_details.append((syllable, tone, missing_sp))

    print(f"Syllables with missing recordings: {len(missing_details)}")
    for syllable, tone, sp_list in missing_details[:30]:
        print(f"  {syllable} tone {tone}: missing {', '.join(sp_list)}")
    if len(missing_details) > 30:
        print(f"  ...and {len(missing_details) - 30} more.")

    if unknown_files:
        print(f"\nUnrecognized or out-of-list audio files: {len(unknown_files)}")
        for name in unknown_files[:20]:
            print(f"  {name}")
        if len(unknown_files) > 20:
            print(f"  ...and {len(unknown_files) - 20} more.")


def write_index(index: Dict[str, Dict[str, Dict[str, Optional[Dict]]]], path: Path = OUTPUT_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def main() -> None:
    index, unknown = build_index()
    write_index(index)
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")
    summarize(index, unknown)


if __name__ == "__main__":
    main()
