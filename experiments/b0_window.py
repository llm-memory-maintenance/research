"""B0 Recent Window mechanics: complete exchanges, marginal chat-template counts, suffix selection."""

ACKNOWLEDGEMENT = 'Noted.'
EVENT_ORDER = ('I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7', 'U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'N1', 'U7', 'N2')
REQUIRED_EVENTS = ('U7', 'N2')


def build_exchanges(texts):
    """One complete exchange per event, oldest to newest: the user text plus the fixed acknowledgement."""
    if set(texts) != set(EVENT_ORDER):
        raise ValueError('Expected exactly the 16 CRST information events')
    if any(not isinstance(texts[label], str) or not texts[label] for label in EVENT_ORDER):
        raise ValueError('Event texts must be nonempty strings')
    return [{'event': label,
             'messages': [{'role': 'user', 'content': texts[label]},
                          {'role': 'assistant', 'content': ACKNOWLEDGEMENT}]}
            for label in EVENT_ORDER]


def chat_tokens(messages, tokenizer):
    """Local template token count without an answer-generation prefix."""
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return len(tokenizer.encode(rendered, add_special_tokens=False))


def history_tokens(system, exchanges, tokenizer):
    """T_chat(system + history) - T_chat(system); the system prompt and Q are outside the count."""
    base = [{'role': 'system', 'content': system}]
    history = [message for exchange in exchanges for message in exchange['messages']]
    return chat_tokens(base + history, tokenizer) - chat_tokens(base, tokenizer)


def select_window(exchanges, budget, system, tokenizer):
    """Newest-first contiguous suffix; the whole proposed suffix is counted at each admission.

    Selection reads only exchange messages, never event labels. The first exchange that does not fit
    ends expansion without skipping or truncating; an empty result is a history-unit overflow.
    """
    if type(budget) is not int or budget < 0:
        raise ValueError('Expected a nonnegative integer budget')
    selected = []
    for exchange in reversed(exchanges):
        trial = [exchange] + selected
        if history_tokens(system, trial, tokenizer) > budget:
            break
        selected = trial
    return {'exchanges': selected, 'history_tokens': history_tokens(system, selected, tokenizer),
            'history_unit_overflow': not selected}


def required_suffix(exchanges, required=REQUIRED_EVENTS):
    """Calibration oracle: the shortest newest suffix containing every required event."""
    labels = [exchange['event'] for exchange in exchanges]
    return exchanges[min(labels.index(event) for event in required):]


def required_budget(exchanges, system, tokenizer, required=REQUIRED_EVENTS):
    """Smallest budget at which select_window retains every required event.

    Expansion is newest-first and stops at the first exchange that does not fit, so the required suffix is
    admitted only if every shorter newest suffix also fits: the answer is the largest count among them.
    """
    suffix = required_suffix(exchanges, required)
    return max(history_tokens(system, suffix[-size:], tokenizer) for size in range(1, len(suffix) + 1))


def retains(selection, required=REQUIRED_EVENTS):
    return set(required) <= {exchange['event'] for exchange in selection['exchanges']}


def assemble(system, selection, question):
    """Chat messages for the answer call: system, chronological history, then Q."""
    history = [message for exchange in selection['exchanges'] for message in exchange['messages']]
    return [{'role': 'system', 'content': system}, *history, {'role': 'user', 'content': question}]
