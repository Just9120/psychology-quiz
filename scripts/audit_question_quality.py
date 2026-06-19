#!/usr/bin/env python3
"""Deterministic reporting-only audit for active approved canonical questions."""
from __future__ import annotations
import argparse,json,re,statistics,sys,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
REPO_ROOT=Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from scripts.audit_question_bank import active_topics
NEGATIVE_RE=re.compile(r"\b(не|кроме|исключени|неверн|ошибочн|не относится|не является)\b",re.I)

def normalize_text(text:str)->str:
    return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",str(text)).casefold()).strip()

def iter_questions():
    for topic in sorted(active_topics(), key=lambda t:(t.get('order',0),t.get('id',''))):
        path=REPO_ROOT/topic['question_file']; data=json.loads(path.read_text(encoding='utf-8'))
        for q in data:
            if q.get('status')=='approved': yield topic,q

def inspect_question(q:dict[str,Any])->dict[str,Any]:
    opts=[str(o) for o in q['options']]; ci=int(q['correct_option_index']); lens=[len(o) for o in opts]
    correct_len=lens[ci]; dist=[l for i,l in enumerate(lens) if i!=ci]
    unique_longest=all(correct_len>l for l in dist)
    ratio=correct_len/statistics.median(dist) if dist and statistics.median(dist) else 0
    delta=correct_len-max(dist) if dist else 0
    return {'option_lengths':lens,'unique_longest_correct':unique_longest,'high_severity_length_cue': bool(unique_longest and ratio>=2.75 and delta>=45),'negative_exception_wording': bool(NEGATIVE_RE.search(str(q.get('question',''))))}

def summarize(items:list[tuple[dict[str,Any],dict[str,Any]]])->dict[str,Any]:
    stems=defaultdict(list); optsets=defaultdict(list); pairs=defaultdict(list); dist=Counter(); unique=high=neg=0
    for topic,q in items:
        m=inspect_question(q); unique+=m['unique_longest_correct']; high+=m['high_severity_length_cue']; neg+=m['negative_exception_wording']
        for l in m['option_lengths']: dist[str(l)]+=1
        stems[normalize_text(q['question'])].append(q['id'])
        optsets[tuple(sorted(normalize_text(o) for o in q['options']))].append(q['id'])
        pairs[(normalize_text(q['question']), tuple(normalize_text(o) for o in q['options']))].append(q['id'])
    n=len(items)
    return {'approved_question_count':n,'unique_longest_correct_count':unique,'unique_longest_correct_rate':round(unique/n,4) if n else 0,
            'high_severity_length_cue_count':high,
            'duplicate_normalized_stems':{k:v for k,v in stems.items() if len(v)>1},
            'duplicate_normalized_option_sets':{' | '.join(k):v for k,v in optsets.items() if len(v)>1},
            'exact_duplicate_question_answer_pairs':{' | '.join(k[0:1]+k[1]):v for k,v in pairs.items() if len(v)>1},
            'negative_exception_wording_count':neg,'option_length_distribution':dict(sorted(dist.items(), key=lambda kv:int(kv[0])))}

def build_report()->dict[str,Any]:
    all_items=list(iter_questions()); by=defaultdict(list)
    for t,q in all_items: by[t['id']].append((t,q))
    return {'canonical_source':'content/topics.json active questions contours and referenced JSON question files','global':summarize(all_items),'topics':{tid:summarize(vals) for tid,vals in sorted(by.items())}}

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--report-path'); a=p.parse_args(); r=build_report(); g=r['global']
    print(f"Approved canonical questions: {g['approved_question_count']}"); print(f"Unique-longest-correct: {g['unique_longest_correct_count']} ({g['unique_longest_correct_rate']:.2%})"); print(f"High-severity length cues: {g['high_severity_length_cue_count']}")
    if a.report_path:
        path=Path(a.report_path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
