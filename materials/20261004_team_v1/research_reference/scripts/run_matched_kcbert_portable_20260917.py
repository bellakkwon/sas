#!/usr/bin/env python3
"""Portable offline DUP/FLIP/BASE KcBERT runner for private SAS Compute Python.

The bundle is the sole input boundary. Per-row predictions remain private;
only aggregate metrics are printed. An interrupted run resumes by whole arm.
"""
from __future__ import annotations
import argparse, csv, fcntl, hashlib, importlib.util, json, math, os, random, sys, time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any
import numpy as np

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
try:
    import torch
    from torch.utils.data import Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
except Exception as exc:  # preflight can still explain missing dependencies
    torch = None; Dataset = object; _IMPORT_ERROR = repr(exc)

SEEDS=(42,101,202,303,404); ARMS=("DUP","FLIP","BASE"); BATCH=32; EPOCHS=3; MAXLEN=128; LR=2e-5; WD=.01
REQUIRED_MODEL=("config.json","model.safetensors","tokenizer_config.json","vocab.txt")
REQUIRED_ROWS=("message_id","development_group_id","role","label","has_url","text_model_base")

def req(ok,msg):
    if not ok: raise ValueError(msg)
def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def stable_json(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def schedule(n,e):
    b=math.ceil((n+e)/BATCH); u=EPOCHS*b
    return {'n_original':n,'e_preflight_pass':e,'dup_rows':n+e,'flip_rows':n+e,'base_rows':n,'batch_size':BATCH,'epochs':EPOCHS,'batches_per_epoch':b,'common_update_budget':u,'common_draws':u*BATCH,'padding_per_epoch':b*BATCH-(n+e),'base_replacement':True}

def paths(bundle): return Path(bundle)/'model_rows.csv',Path(bundle)/'edits.csv',Path(bundle)/'manifest.json',Path(bundle)/'checkpoint'
def load_bundle(bundle):
    rows_p, edits_p, man_p, ck=paths(bundle); req(man_p.is_file(),'manifest_missing'); man=json.loads(man_p.read_text())
    req(man.get('schema_version') in (1,'1.0'),'manifest_schema'); req(rows_p.is_file() and edits_p.is_file(),'input_missing')
    req(man.get('status')=='private_transfer_bundle_not_remote_verified','bundle_status_drift')
    req(man.get('privacy',{}).get('reviewed_actual_pii_groups_excluded') is True,'privacy_manifest_missing')
    req(man.get('protocol',{}).get('E_status')=='post_return_exploratory_preflight_pass_not_prospective_approval','E_status_drift')
    for p in (rows_p,edits_p):
        entry=man.get('files',{}).get(p.name,{}); expected=entry.get('sha256'); req(expected and digest(p)==expected and p.stat().st_size==entry.get('bytes'),'bundle_hash_mismatch:'+p.name)
    for n in REQUIRED_MODEL:
        p=ck/n; req(p.is_file(),'checkpoint_missing:'+n); entry=man.get('files',{}).get('checkpoint/'+n,{}); req(entry.get('sha256') and digest(p)==entry['sha256'] and p.stat().st_size==entry.get('bytes'),'bundle_hash_mismatch:checkpoint/'+n)
    for p in (Path(bundle),ck,man_p,rows_p,edits_p,*(ck/n for n in REQUIRED_MODEL)):
        req(not p.is_symlink() and p.stat().st_mode & 0o077 == 0,'private_bundle_permissions_or_symlink')
    with rows_p.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream); req(tuple(reader.fieldnames or ())==REQUIRED_ROWS,'row_schema'); rows=list(reader)
    with edits_p.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream); req(tuple(reader.fieldnames or ())==('message_id','edited_text','base_sha256','edited_sha256'),'edit_schema'); edits=list(reader)
    req(rows and edits,'empty_bundle_data')
    req(len({r['message_id'] for r in rows})==len(rows),'duplicate_row_id'); req(len({e['message_id'] for e in edits})==len(edits),'duplicate_edit_id')
    req({r['role'] for r in rows}== {'fit','threshold_calibration','development_readout'},'invalid_role')
    groups={}
    for r in rows:
        req(r['message_id'] and r['development_group_id'] and r['text_model_base'],'empty_required_field')
        req(r['label'] in ('normal','smishing') and r['has_url'] in ('0','1'),'invalid_label_or_url')
        req(groups.setdefault(r['development_group_id'],r['role'])==r['role'],'group_role_leakage')
    by={r['message_id']:r for r in rows if r['role']=='fit'}; ordered=[]
    for e in edits:
        r=by.get(e['message_id']); req(r is not None,'edit_not_fit'); req(digest_text(r['text_model_base'])==e['base_sha256'],'edit_base_hash_mismatch'); req(digest_text(e['edited_text'])==e['edited_sha256'],'edit_hash_mismatch'); req(e['edited_text']!=r['text_model_base'],'edit_noop'); ordered.append((r,e))
    held={r['text_model_base'] for r in rows if r['role']!='fit'}
    req(not any(e['edited_text'] in held for _,e in ordered),'edited_text_holdout_collision')
    counts=man.get('counts',{}); req(counts.get('rows')==len(rows) and counts.get('edits')==len(ordered) and all(counts.get(role)==sum(r['role']==role for r in rows) for role in ('fit','threshold_calibration','development_readout')),'manifest_count_mismatch')
    req(man['protocol'].get('common_updates')==schedule(counts['fit'],counts['edits'])['common_update_budget'],'budget_manifest_drift')
    return rows,ordered,man,ck
def digest_text(x): return hashlib.sha256(x.encode()).hexdigest()

def threshold(y,p,cap=.01):
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float); req(len(y)==len(p) and set(y)<= {0,1},'bad_scores'); normal=int((y==0).sum()); mal=int((y==1).sum()); req(normal and mal,'calibration_requires_both_classes')
    feasible=[]
    for t in np.append(np.unique(p),np.nextafter(p.max(),np.inf)):
        pred=p>=t; fp=int(((y==0)&pred).sum()); tp=int(((y==1)&pred).sum())
        if fp/normal<=cap: feasible.append((tp,fp,float(t)))
    req(feasible,'no_feasible_threshold'); tp,fp,t=max(feasible,key=lambda z:(z[0],-z[1],z[2]))
    return t,{'normal_rows':normal,'malicious_rows':mal,'normal_fp':fp,'normal_fpr':fp/normal,'malicious_tp':tp,'malicious_recall':tp/mal,'candidate_count':len(np.unique(p))+1}

def aggregate_preflight(bundle):
    rows,edits,man,ck=load_bundle(bundle)
    fit=sum(r['role']=='fit' for r in rows)
    cal=sum(r['role']=='threshold_calibration' for r in rows)
    read=sum(r['role']=='development_readout' for r in rows)
    visible=None
    if torch is not None:
        tokenizer=AutoTokenizer.from_pretrained(str(ck),local_files_only=True)
        originals=[r['text_model_base'] for r,_ in edits]
        altered=[e['edited_text'] for _,e in edits]
        before=tokenizer(originals,truncation=True,padding='max_length',max_length=MAXLEN)
        after=tokenizer(altered,truncation=True,padding='max_length',max_length=MAXLEN)
        visible=sum(before['input_ids'][i]!=after['input_ids'][i] or
                    before['attention_mask'][i]!=after['attention_mask'][i]
                    for i in range(len(edits)))
        req(visible==len(edits),'token_invisible_edit_in_bundle')
    return {
        'status':'preflight_no_training',
        'bundle_manifest_sha256':digest(paths(bundle)[2]),
        'rows':{'total':len(rows),'fit':fit,'calibration':cal,'readout':read},
        'edits':{'preflight_pass':len(edits),'token_visible':visible,'prospective_approval':False},
        'schedule':schedule(fit,len(edits)),
        'seeds':list(SEEDS),'arms':list(ARMS),
        'checkpoint_sha256':man['files']['checkpoint/model.safetensors']['sha256'],
        'dependencies_available':torch is not None,
        'dependency_error':None if torch is not None else _IMPORT_ERROR,
        'device_available':{'cpu':True,
                            'cuda':bool(torch and torch.cuda.is_available()),
                            'mps':bool(torch and hasattr(torch.backends,'mps') and torch.backends.mps.is_available())},
        'network':'disabled_local_files_only',
    }

def load_store():
    path = Path(__file__).with_name('kcbert_private_store_20260917.py')
    req(path.is_file(), 'private_store_module_missing')
    spec = importlib.util.spec_from_file_location('kcbert_private_store', path)
    req(spec is not None and spec.loader is not None, 'private_store_import_failed')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def choose_device(name):
    req(torch is not None, 'torch_or_transformers_unavailable')
    cuda = torch.cuda.is_available()
    mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
    if name == 'auto':
        name = 'cuda' if cuda else 'mps' if mps else 'cpu'
    req(name == 'cpu' or name == 'cuda' and cuda or name == 'mps' and mps,
        'requested_device_unavailable')
    return torch.device(name)


def seed_all(value):
    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(value)


def class_weights(fit_labels):
    y = np.asarray(fit_labels, dtype=int)
    normal, malicious = int((y == 0).sum()), int((y == 1).sum())
    req(normal > 0 and malicious > 0, 'fit_requires_both_classes')
    return {0: len(y) / (2 * normal), 1: len(y) / (2 * malicious)}


def arm_indices(row_count, updates, seed_value, replacement):
    rng = np.random.default_rng(seed_value)
    for _ in range(EPOCHS):
        if replacement:
            yield rng.choice(row_count, size=(updates // EPOCHS) * BATCH, replace=True)
        else:
            yield np.resize(np.arange(row_count), math.ceil(row_count / BATCH) * BATCH)


def exposure_summary(labels, weights, updates, seed_value, replacement):
    y = np.asarray(labels, dtype=int)
    draw = np.concatenate(list(arm_indices(len(y), updates, seed_value, replacement)))
    req(len(draw) == updates * BATCH, 'exposure_budget_mismatch')
    return {
        'draws': len(draw), 'normal_draws': int((y[draw] == 0).sum()),
        'smishing_draws': int((y[draw] == 1).sum()),
        'weighted_loss_mass': float(np.asarray(weights, dtype=float)[draw].sum()),
    }


def train_arm(texts, labels, weights, tokenizer, device, checkpoint,
              updates, seed_value, replacement=False, max_updates=None):
    seed_all(seed_value)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(checkpoint), local_files_only=True, num_labels=2,
        ignore_mismatched_sizes=True,
    ).to(device)
    encoded = tokenizer(texts, truncation=True, padding='max_length',
                        max_length=MAXLEN, return_tensors='pt')
    y = torch.tensor(labels, dtype=torch.long)
    w = torch.tensor(weights, dtype=torch.float32)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, max(1, int(updates * .1)), updates,
    )
    model.train()
    step = 0
    for epoch_indices in arm_indices(len(texts), updates, seed_value, replacement):
        for start in range(0, len(epoch_indices), BATCH):
            indexes = epoch_indices[start:start + BATCH]
            batch = {key: value[indexes].to(device) for key, value in encoded.items()}
            logits = model(**batch).logits
            loss = (w[indexes].to(device) * torch.nn.functional.cross_entropy(
                logits, y[indexes].to(device), reduction='none',
            )).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            step += 1
            if max_updates is not None and step >= max_updates:
                return model, step
    req(step == updates, 'training_update_budget_mismatch')
    return model, step


def infer(model, rows, tokenizer, device):
    texts = [row['text_model_base'] for row in rows]
    probabilities = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(texts), BATCH):
            encoded = tokenizer(texts[start:start + BATCH], truncation=True,
                                padding='max_length', max_length=MAXLEN,
                                return_tensors='pt')
            logits = model(**{key: value.to(device) for key, value in encoded.items()}).logits
            probabilities.extend(torch.softmax(logits, dim=1)[:, 1].cpu().tolist())
    req(len(probabilities) == len(rows) and all(np.isfinite(probabilities)),
        'inference_probability_invalid')
    return probabilities


def prediction_rows(rows, probabilities, role):
    req(len(rows) == len(probabilities), 'prediction_row_count_mismatch')
    return [
        {'message_id': row['message_id'],
         'development_group_id': row['development_group_id'],
         'role': role, 'label': row['label'], 'has_url': row['has_url'],
         'probability': repr(float(probability))}
        for row, probability in zip(rows, probabilities)
    ]


def run_spec(bundle, device_name, versions):
    return {
        'bundle_manifest_sha256': digest(paths(bundle)[2]),
        'runner_sha256': digest(Path(__file__)),
        'store_sha256': digest(Path(__file__).with_name('kcbert_private_store_20260917.py')),
        'checkpoint_sha256': digest(paths(bundle)[3] / 'model.safetensors'),
        'device': device_name, 'versions': versions,
        'protocol': {'seeds': list(SEEDS), 'arms': list(ARMS), 'batch': BATCH,
                     'epochs': EPOCHS, 'max_length': MAXLEN, 'lr': LR,
                     'weight_decay': WD, 'warmup_ratio': .1,
                     'fpr_calibration_ceiling': .01,
                     'gradient_clip_norm': 1.0, 'precision': 'fp32'},
    }


def fingerprint(spec):
    return hashlib.sha256(stable_json(spec).encode()).hexdigest()


def versions_now():
    import importlib.metadata
    return {'python': sys.version.split()[0], 'torch': importlib.metadata.version('torch'),
            'transformers': importlib.metadata.version('transformers'),
            'numpy': importlib.metadata.version('numpy')}


def expected_prediction_metadata(calibration, readout):
    def metadata(rows, role):
        return [{**{key: row[key] for key in ('message_id','development_group_id','label','has_url')},
                 'role': role} for row in rows]
    return {'calibration': metadata(calibration, 'calibration'),
            'readout': metadata(readout, 'readout')}


def initialize_output(output, bundle, spec, fp, exposures):
    output = Path(output)
    req(not output.is_symlink(), 'output_symlink_forbidden')
    req(output.resolve() != Path(bundle).resolve() and
        Path(bundle).resolve() not in output.resolve().parents,
        'output_inside_input_bundle')
    manifest_path = output / 'run_manifest.json'
    if output.exists():
        req(output.is_dir() and output.stat().st_mode & 0o077 == 0,
            'output_permissions_or_type')
        req(manifest_path.is_file(), 'nonempty_or_partial_output_without_manifest')
        stored = json.loads(manifest_path.read_text(encoding='utf-8'))
        req(stored.get('fingerprint') == fp and stored.get('spec') == spec,
            'resume_fingerprint_mismatch')
    else:
        req(output.parent.is_dir() and not output.parent.is_symlink() and
            output.parent.stat().st_mode & 0o077 == 0,
            'private_output_parent_missing_or_too_open')
        output.mkdir(mode=0o700)
        os.chmod(output, 0o700)
        stored = {'schema_version': 1, 'status': 'in_progress', 'fingerprint': fp,
                  'spec': spec, 'exposures': exposures,
                  'E_status': 'post_return_exploratory_not_prospective_approval'}
        with manifest_path.open('x', encoding='utf-8') as stream:
            json.dump(stored, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
        os.chmod(manifest_path, 0o600)
    return stored


@contextmanager
def exclusive_output_lock(output):
    output = Path(output)
    parent = output.parent
    req(parent.is_dir() and not parent.is_symlink() and
        parent.stat().st_mode & 0o077 == 0,
        'private_output_parent_missing_or_too_open')
    lock_path = parent / f'.{output.name}.run.lock'
    req(not lock_path.is_symlink(), 'run_lock_symlink_forbidden')
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('concurrent_run_for_same_output') from exc
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def locked_run(function):
    @wraps(function)
    def wrapped(bundle, output, *args, **kwargs):
        bundle_path = Path(bundle).resolve()
        output_path = Path(output).resolve()
        req(output_path != bundle_path and bundle_path not in output_path.parents,
            'output_inside_input_bundle')
        with exclusive_output_lock(output):
            return function(bundle, output, *args, **kwargs)
    return wrapped


@locked_run
def run_full(bundle, output, device_name='auto', max_arms=1, threads=4,
             allow_cpu_full_run=False):
    req(torch is not None, 'torch_or_transformers_unavailable')
    req(max_arms > 0 and threads > 0, 'invalid_run_limits')
    aggregate_preflight(bundle)
    rows, edits, _, checkpoint = load_bundle(bundle)
    device = choose_device(device_name)
    req(device.type != 'cpu' or allow_cpu_full_run,
        'cpu_full_run_requires_explicit_allow_cpu_full_run')
    torch.set_num_threads(threads)
    fit = [row for row in rows if row['role'] == 'fit']
    calibration = [row for row in rows if row['role'] == 'threshold_calibration']
    readout = [row for row in rows if row['role'] == 'development_readout']
    fit_labels = [int(row['label'] == 'smishing') for row in fit]
    weights_by_class = class_weights(fit_labels)
    originals = [row['text_model_base'] for row in fit]
    selected_labels = [int(row['label'] == 'smishing') for row, _ in edits]
    duplicated_labels = fit_labels + selected_labels
    arm_texts = {
        'DUP': originals + [row['text_model_base'] for row, _ in edits],
        'FLIP': originals + [edit['edited_text'] for _, edit in edits],
        'BASE': originals,
    }
    arm_labels = {'DUP': duplicated_labels, 'FLIP': duplicated_labels, 'BASE': fit_labels}
    budget = schedule(len(fit), len(edits))['common_update_budget']
    exposures = {}
    for seed_value in SEEDS:
        for arm in ARMS:
            labels = arm_labels[arm]
            weights = [weights_by_class[value] for value in labels]
            exposures[f'{seed_value}_{arm}'] = exposure_summary(
                labels, weights, budget, seed_value, arm == 'BASE',
            )
    spec = run_spec(bundle, str(device), {**versions_now(), 'threads': threads})
    fp = fingerprint(spec)
    initialize_output(output, bundle, spec, fp, exposures)
    store = load_store()
    expected = expected_prediction_metadata(calibration, readout)
    tokenizer = AutoTokenizer.from_pretrained(str(checkpoint), local_files_only=True)
    completed_before = 0
    trained_now = 0
    for seed_value in SEEDS:
        for arm in ARMS:
            arm_dir = Path(output) / f'seed_{seed_value}' / arm
            if arm_dir.exists():
                store.verify_arm(output, seed_value, arm, fp, expected)
                completed_before += 1
                continue
            if trained_now >= max_arms:
                continue
            labels = arm_labels[arm]
            weights = [weights_by_class[value] for value in labels]
            model, updates = train_arm(
                arm_texts[arm], labels, weights, tokenizer, device, checkpoint,
                budget, seed_value, replacement=arm == 'BASE',
            )
            req(updates == budget, 'arm_update_budget_mismatch')
            cal_predictions = prediction_rows(
                calibration, infer(model, calibration, tokenizer, device), 'calibration',
            )
            read_predictions = prediction_rows(
                readout, infer(model, readout, tokenizer, device), 'readout',
            )
            store.write_arm(output, seed_value, arm, cal_predictions, read_predictions, fp)
            store.verify_arm(output, seed_value, arm, fp, expected)
            del model
            trained_now += 1
    complete = sum((Path(output) / f'seed_{seed_value}' / arm).is_dir()
                   for seed_value in SEEDS for arm in ARMS)
    result = {'status': 'partial_private_run' if complete < len(SEEDS) * len(ARMS)
              else 'completed_15_arms_checked',
              'fingerprint': fp, 'completed_arms': complete,
              'trained_this_invocation': trained_now,
              'reused_completed_arms': completed_before,
              'prospective_E_approval': False,
              'research_scope': 'single_corpus_internal_development_exploratory'}
    if complete == len(SEEDS) * len(ARMS):
        checked = store.check(output, fp)
        checked['E_status'] = 'post_return_exploratory_not_prospective_approval'
        checked['evaluation_role'] = 'development_readout_not_independent_test'
        for seed_value in SEEDS:
            for arm in ARMS:
                store.verify_arm(output, seed_value, arm, fp, expected)
        report_path = Path(output) / 'aggregate_report.json'
        content = json.dumps(checked, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        if report_path.exists():
            req(report_path.read_text(encoding='utf-8') == content,
                'aggregate_report_drift')
        else:
            with report_path.open('x', encoding='utf-8') as stream:
                stream.write(content)
            os.chmod(report_path, 0o600)
        manifest_path = Path(output) / 'run_manifest.json'
        current = json.loads(manifest_path.read_text(encoding='utf-8'))
        req(current['fingerprint'] == fp and current['status'] in ('in_progress','completed'),
            'completion_manifest_drift')
        if current['status'] != 'completed':
            current['status'] = 'completed'
            staging = manifest_path.with_name('.run_manifest_complete.tmp')
            with staging.open('x', encoding='utf-8') as stream:
                json.dump(current, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write('\n')
            os.chmod(staging, 0o600)
            os.replace(staging, manifest_path)
    return result


def check_full(bundle, output):
    rows, _, _, _ = load_bundle(bundle)
    manifest_path = Path(output) / 'run_manifest.json'
    req(manifest_path.is_file(), 'run_manifest_missing')
    saved = json.loads(manifest_path.read_text(encoding='utf-8'))
    req(saved.get('status') == 'completed', 'run_not_marked_completed')
    spec = saved['spec']
    req(spec['bundle_manifest_sha256'] == digest(paths(bundle)[2]) and
        spec['runner_sha256'] == digest(Path(__file__)) and
        spec['store_sha256'] == digest(Path(__file__).with_name('kcbert_private_store_20260917.py')) and
        spec['checkpoint_sha256'] == digest(paths(bundle)[3] / 'model.safetensors') and
        fingerprint(spec) == saved['fingerprint'], 'run_fingerprint_drift')
    store = load_store()
    checked = store.check(output, saved['fingerprint'])
    checked['E_status'] = 'post_return_exploratory_not_prospective_approval'
    checked['evaluation_role'] = 'development_readout_not_independent_test'
    calibration = [row for row in rows if row['role'] == 'threshold_calibration']
    readout = [row for row in rows if row['role'] == 'development_readout']
    expected = expected_prediction_metadata(calibration, readout)
    for seed_value in SEEDS:
        for arm in ARMS:
            store.verify_arm(output, seed_value, arm, saved['fingerprint'], expected)
    content = json.dumps(checked, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    report_path = Path(output) / 'aggregate_report.json'
    req(report_path.is_file() and report_path.read_text(encoding='utf-8') == content,
        'aggregate_report_readback_drift')
    return {'status': 'completed_15_arms_checked', 'fingerprint': saved['fingerprint'],
            'completed_arms': len(SEEDS) * len(ARMS),
            'aggregate_report_sha256': digest(report_path),
            'prospective_E_approval': False}


def smoke(bundle, device_name='auto', threads=4):
    req(torch is not None, 'torch_or_transformers_unavailable')
    rows, edits, _, checkpoint = load_bundle(bundle)
    device = choose_device(device_name)
    torch.set_num_threads(threads)
    fit = [row for row in rows if row['role'] == 'fit']
    labels = [int(row['label'] == 'smishing') for row in fit]
    weights_by_class = class_weights(labels)
    labels += [int(row['label'] == 'smishing') for row, _ in edits]
    texts = [row['text_model_base'] for row in fit] + [row['text_model_base'] for row, _ in edits]
    tokenizer = AutoTokenizer.from_pretrained(str(checkpoint), local_files_only=True)
    started = time.monotonic()
    _, updates = train_arm(texts, labels, [weights_by_class[y] for y in labels],
                           tokenizer, device, checkpoint,
                           schedule(len(fit), len(edits))['common_update_budget'],
                           SEEDS[0], max_updates=2)
    return {'status': 'smoke_no_research_result', 'device': str(device),
            'seed': SEEDS[0], 'arm': 'DUP', 'updates': updates,
            'elapsed_seconds': round(time.monotonic() - started, 2),
            'private_predictions_written': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--preflight', action='store_true')
    action.add_argument('--smoke', action='store_true')
    action.add_argument('--run', action='store_true')
    action.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--device', default='auto', choices=('auto','cpu','mps','cuda'))
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--max-arms', type=int, default=1)
    parser.add_argument('--allow-cpu-full-run', action='store_true')
    args = parser.parse_args()
    if args.preflight:
        result = aggregate_preflight(args.bundle)
    elif args.smoke:
        result = smoke(args.bundle, args.device, args.threads)
    elif args.run:
        req(args.output is not None, 'output_required_for_run')
        result = run_full(args.bundle, args.output, args.device,
                          args.max_arms, args.threads, args.allow_cpu_full_run)
    else:
        req(args.output is not None, 'output_required_for_check')
        result = check_full(args.bundle, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
