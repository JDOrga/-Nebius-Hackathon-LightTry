"""Request-state constraints, not a general natural-language interpreter.

Only full-string, enumerated commands are recognized here. All other intent
and preset reasoning remain the model's job. Unknown exclusion changes fail
closed; users can use the explicit exclusion controls to disambiguate.
"""
import re

ALIASES = {'sunny': 'sunny', '晴日公园': 'sunny', 'sunrise': 'sunrise',
           '粉色晨光': 'sunrise', 'street': 'street', '夜景': 'street', '夜间街灯': 'street'}


def exact_operation(text):
    text = text.strip().lower().rstrip('。.!！')
    text = re.sub(r'(?:[,，;；]|\s)+(?:请)?(?:用中文(?:回答|回复)|用英文(?:回答|回复)|(?:reply|respond|answer) in (?:english|chinese))$', '', text).strip()
    if text in ALIASES:
        return {'type': 'select', 'ids': [ALIASES[text]]}
    if text in ('把第二个去掉', '删掉第二项', '删除第二项', 'remove the second'):
        return {'type': 'remove', 'index': 1}
    if text in ('换成另一种', 'another one'):
        return {'type': 'replace_other'}
    for name, preset in ALIASES.items():
        if text in (f'只选 {name}', f'只选{name}', f'only {name}', f'select only {name}'):
            return {'type': 'select', 'ids': [preset]}
        if text in (f'不要{name}', f'不要再推荐{name}', f'exclude {name}', f'no {name}'):
            return {'type': 'exclude', 'ids': [preset]}
        if text in (f'解除{name}排除', f'允许推荐{name}', f'allow {name}', f'unexclude {name}'):
            return {'type': 'unexclude', 'ids': [preset]}
    if text == 'no night':
        return {'type': 'exclude', 'ids': ['street']}
    return None


def response_language(text, product_language='zh'):
    # Explicit, conventional language requests win. Mixed/no explicit request
    # uses the product setting. Do not infer English from preset identifiers.
    requests = list(re.finditer(r'用中文(?:回答|回复)|用英文(?:回答|回复)|'
                               r'(?:reply|respond|answer) in (?:english|chinese)', text, re.I))
    if requests:
        last = requests[-1].group().lower()
        return 'en' if '英文' in last or 'english' in last else 'zh'
    return product_language


def constraints(current, operation):
    result = {'excludedIds': current['excludedIds'][:], 'operation': operation}
    if not operation:
        return result
    kind = operation['type']
    chosen, excluded = current['presetIds'][:], current['excludedIds'][:]
    if kind == 'select':
        result['presetIds'] = operation['ids']
    elif kind == 'remove':
        index = operation['index']
        result['presetIds'] = [item for n, item in enumerate(chosen) if n != index]
    elif kind == 'replace':
        result['presetIds'] = [operation['id'] if n == operation['index'] else item for n, item in enumerate(chosen)]
    elif kind == 'replace_other':
        result['differentFrom'] = chosen
    elif kind == 'exclude':
        result['excludedIds'] = list(dict.fromkeys(excluded + operation['ids']))
        kept = [item for item in chosen if item not in result['excludedIds']]
        if kept:
            result['presetIds'] = kept
    elif kind == 'unexclude':
        result['excludedIds'] = [item for item in excluded if item not in operation['ids']]
        if chosen:
            result['presetIds'] = chosen
    return result


def semantic_check(plan, required):
    if set(plan['excludedIds']) != set(required['excludedIds']):
        return False
    if 'presetIds' in required:
        expected = required['presetIds']
        # Empty selection cannot be encoded as ready in the existing protocol.
        # Clarify instead of inventing an alternative or an exclusion.
        return (plan['presetIds'] == expected and
                plan['status'] == ('ready' if expected else 'clarification'))
    if 'differentFrom' in required:
        return (plan['status'] == 'ready' and bool(plan['presetIds']) and
                not set(plan['presetIds']) & set(required['differentFrom']))
    return True


def language_review(plan, expected):
    """Conservative script check per reason/question. Quality needs human review.

    IDs/model names and technical acronyms are permitted; mixed ordinary English
    prose is flagged for review, not assumed good because it contains Han text.
    Unsupported codes have no model prose; the UI localizes their descriptions.
    """
    states = []
    for text in plan['reasons'] + ([plan['question']] if plan['question'] else []):
        clean = re.sub(r'\b(?:sunny|sunrise|street|Nemotron|NVIDIA|HDR|GPU|AI|ID)\b', '', text, flags=re.I)
        han = len(re.findall(r'[\u4e00-\u9fff]', clean))
        words = re.findall(r'[A-Za-z]{2,}', clean)
        if expected == 'zh':
            states.append('fail' if not han and words else 'review' if words or not han else 'pass')
        else:
            states.append('fail' if han >= 3 and not words else 'review' if han or not words else 'pass')
    return 'fail' if 'fail' in states else 'review' if 'review' in states else 'pass' if states else 'not-applicable'
