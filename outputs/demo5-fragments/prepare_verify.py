"""Local exact-overlap assembly simulation preparation and independent verification."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import sys
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import FeatureLocation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/demo5-fragments'
sources = [ROOT / 'inputs/pEGFP-N1.gb', ROOT / 'inputs/mCherry.gb']
v, d = [SeqIO.read(p, 'genbank') for p in sources]
# Normalize source bases too: product-only normalization breaks feature comparisons.
for record in (v, d):
    record.seq = record.seq.upper()
egfp, = [f for f in v.features if f.type == 'CDS' and f.qualifiers.get('label') == ['EGFP']]
cherry, = [f for f in d.features if f.type == 'CDS' and f.qualifiers.get('label') == ['mCherry']]
a, b = int(egfp.location.start), int(egfp.location.end)
assert egfp.location.strand == cherry.location.strand == 1
assert egfp.extract(v.seq) == v.seq[a:b]
for rec, feat in [(v, egfp), (d, cherry)]:
    assert str(feat.extract(rec.seq).translate(cds=True)) == feat.qualifiers['translation'][0]
cds = cherry.extract(d.seq)
backseq = v.seq[b:] + v.seq[:a]
left, right = backseq[-25:], backseq[:25]
expected = backseq + cds
unaffected = [f for f in v.features if f is not egfp and f.type != 'source']

def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}

def prepare():
    backbone = SeqRecord(backseq, id='demo5_backbone', description='Simulation backbone: pEGFP-N1 bases 1399..4733 then 1..678; complete EGFP removed.')
    backbone.annotations = {'molecule_type': 'DNA', 'topology': 'linear'}
    for original in v.features:
        if original is egfp:
            continue
        f = deepcopy(original)
        if f.type == 'source':
            f.location = FeatureLocation(0, len(backseq), strand=1)
        else:
            start, end = int(f.location.start), int(f.location.end)
            assert end <= a or start >= b
            f.location = f.location + (-b if start >= b else len(v)-b)
        backbone.features.append(f)
    insert = SeqRecord(left + cds + right, id='demo5_mCherry', description='Simulation fragment: 25 bp upstream backbone homology + complete forward mCherry CDS + 25 bp downstream backbone homology; no primer design.')
    insert.annotations = {'molecule_type': 'DNA', 'topology': 'linear'}
    for original in d.features:
        f = deepcopy(original)
        f.location = f.location + 25
        insert.features.append(f)
    for rec, filename in [(backbone, 'backbone-no-EGFP.gb'), (insert, 'mCherry-overlaps.gb')]:
        SeqIO.write(rec, OUT / filename, 'genbank')
    report = {
        'coordinate_convention': '1-based inclusive for reported coordinates',
        'EGFP': {'location': str(egfp.location), 'bases': [a+1,b], 'length': len(egfp), 'complete_translation_verified': True},
        'mCherry': {'bases': [1,711], 'length': len(cds), 'strand': '+', 'complete_translation_verified': True},
        'backbone_derivation': 'pEGFP-N1[1399..4733] + pEGFP-N1[1..678], forward',
        'insert_derivation': 'pEGFP-N1[654..678] + mCherry CDS[1..711] + pEGFP-N1[1399..1423], forward',
        'fragment_lengths': [len(backbone),len(insert)], 'overlaps': [25,25],
        'overlap_sequences_5to3': [str(left),str(right)],
        'expected_product_length': len(expected),
        'product_origin': 'pEGFP-N1 base 1399',
        'source_annotation_handling': 'Vector source retained over derived backbone; donor source retained over mCherry CDS. All 11 unaffected vector features retain qualifiers and extracted sequences.',
        'source_sha256': hashes(), 'errors': []}
    (OUT / 'derivation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

def verify(path):
    p = SeqIO.read(path, 'snapgene' if str(path).endswith('.dna') else 'genbank')
    p.seq = p.seq.upper()  # SnapGene stores lowercase bases; case is not sequence identity.
    assert str(p.seq).upper() == str(expected).upper()
    assert len(p) == 4733-720+711 == 4724
    assert p.annotations['topology'] == 'circular'
    m, = [f for f in p.features if f.type == 'CDS' and f.qualifiers.get('label') == ['mCherry']]
    assert m.extract(p.seq) == cds
    assert str(m.extract(p.seq).translate(cds=True)) == cherry.qualifiers['translation'][0]
    assert int(m.location.start) == len(backseq) and int(m.location.end) == len(p)
    assert not any(f.qualifiers.get('label') == ['EGFP'] for f in p.features)
    for original in unaffected:
        f, = [f for f in p.features if f.qualifiers.get('label') == original.qualifiers.get('label')]
        assert f.type == original.type and f.location.strand == original.location.strand
        assert f.extract(p.seq) == original.extract(v.seq)
        if not str(path).endswith('.dna'):
            assert f.qualifiers == original.qualifiers
    assert p.seq[len(backseq)-25:len(backseq)+25] == left + cds[:25]
    assert p.seq[-25:] + p.seq[:25] == cds[-25:] + right
    junctions = [f for f in p.features if f.qualifiers.get('label', [''])[0].startswith('Gibson junction')]
    assert len(junctions) == 2
    assert [str(f.extract(p.seq)) for f in junctions] == [str(left),str(right)]
    report = json.loads((OUT / 'derivation.json').read_text())
    assert report['source_sha256'] == hashes()
    seq = str(p.seq).upper()
    sites = [i+1 for i in range(len(seq)) if (seq+seq[:5])[i:i+6] == 'GAATTC']
    result = {'path': str(path), 'length': len(p), 'mCherry_bases': [len(backseq)+1,len(p)], 'mCherry_protein_aa': len(cds.translate(cds=True)), 'both_junctions_exact': True, 'complete_sequence_matches': True, 'unaffected_features_verified': len(unaffected), 'EcoRI_motif_starts_1based': sites, 'sources_unchanged': True, 'errors': []}
    print(json.dumps(result, indent=2))
    target = OUT / ('verification-dna.json' if str(path).endswith('.dna') else 'verification-genbank.json')
    target.write_text(json.dumps(result, indent=2)+'\n')

if __name__ == '__main__':
    if len(sys.argv) == 1:
        prepare()
    else:
        verify(Path(sys.argv[1]))
