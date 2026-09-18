HONEYPOT_FIELD = 'homepage'
TRAP_PATH = '/nids-trap/'

BUILTIN_UA_KEYWORDS = (
    'googlebot',
    'bingbot',
    'yandex',
    'baiduspider',
    'curl',
    'wget',
    'python-requests',
    'httpclient',
    'scrapy',
    'go-http-client',
    'sqlmap',
    'nuclei',
    'masscan',
    'headlesschrome',
    'selenium',
    'playwright',
    'puppeteer',
    'phantomjs',
)

SCANNER_PATHS = frozenset(
    {
        '/.env',
        '/wp-login.php',
        '/xmlrpc.php',
        '/.git/config',
    }
)


def _norm_path(path):
    return (path or '').split('?')[0].lower()


UA_KEYWORD_MAX_LEN = 200
UA_KEYWORDS_MAX_CHARS = 4000


def parse_ua_keywords(raw):
    seen = []
    found = set()
    for line in str(raw or '').splitlines():
        item = line.strip().lower()
        if not item or item in found:
            continue
        found.add(item)
        seen.append(item)
    return seen


def extra_ua_keywords(policy):
    return parse_ua_keywords((policy or {}).get('bot_ua_keywords'))


def dump_ua_keywords(keywords):
    return '\n'.join(keywords)


def add_ua_keyword(raw, keyword):
    item = (keyword or '').strip().lower()
    if not item:
        return None, 'Keyword is required.'
    if len(item) > UA_KEYWORD_MAX_LEN:
        return None, 'Keyword is too long.'
    if item in BUILTIN_UA_KEYWORDS:
        return None, 'That keyword is already built in.'
    keywords = parse_ua_keywords(raw)
    if item in keywords:
        return None, 'That keyword is already added.'
    keywords.append(item)
    text = dump_ua_keywords(keywords)
    if len(text) > UA_KEYWORDS_MAX_CHARS:
        return None, 'Keyword list is too long.'
    return text, None


def remove_ua_keyword(raw, keyword):
    item = (keyword or '').strip().lower()
    keywords = [entry for entry in parse_ua_keywords(raw) if entry != item]
    return dump_ua_keywords(keywords)


def extra_path_keywords(policy):
    return parse_ua_keywords((policy or {}).get('bot_path_keywords'))


def add_path_keyword(raw, keyword):
    item = (keyword or '').strip().lower()
    if not item:
        return None, 'Keyword is required.'
    if len(item) > UA_KEYWORD_MAX_LEN:
        return None, 'Keyword is too long.'
    keywords = parse_ua_keywords(raw)
    if item in keywords:
        return None, 'That keyword is already added.'
    keywords.append(item)
    text = dump_ua_keywords(keywords)
    if len(text) > UA_KEYWORDS_MAX_CHARS:
        return None, 'Keyword list is too long.'
    return text, None


def remove_path_keyword(raw, keyword):
    item = (keyword or '').strip().lower()
    keywords = [entry for entry in parse_ua_keywords(raw) if entry != item]
    return dump_ua_keywords(keywords)


def is_trap_path(path):
    value = _norm_path(path).rstrip('/')
    return value == '/nids-trap'


def is_scanner_path(path):
    value = _norm_path(path)
    if value in SCANNER_PATHS:
        return True
    stripped = value.rstrip('/')
    return stripped in {item.rstrip('/') for item in SCANNER_PATHS}


def path_contains_keyword(path, policy):
    keywords = extra_path_keywords(policy)
    if not keywords:
        return False
    value = _norm_path(path)
    for keyword in keywords:
        if keyword in value:
            return True
    return False


def should_trap_path(path, policy):
    policy = policy or {}
    if is_trap_path(path):
        return bool(policy.get('bot_block_scanner_paths') or policy.get('bot_block_webdriver'))
    if is_scanner_path(path):
        return bool(policy.get('bot_block_scanner_paths'))
    if path_contains_keyword(path, policy):
        return True
    return False


def is_bot_user_agent(user_agent, policy):
    policy = policy or {}
    ua = (user_agent or '').strip()
    if not ua:
        return bool(policy.get('bot_block_empty_ua'))
    lowered = ua.lower()
    for keyword in BUILTIN_UA_KEYWORDS:
        if keyword in lowered:
            return True
    for keyword in extra_ua_keywords(policy):
        if keyword in lowered:
            return True
    return False


REASON_EMPTY_UA = 'empty-ua'
REASON_UA = 'ua'
REASON_PATH = 'path'
REASON_HONEYPOT = 'honeypot'
REASON_LISTED = 'listed'

BOT_REASON_LABELS = {
    REASON_EMPTY_UA: 'Empty User-Agent',
    REASON_UA: 'User-Agent',
    REASON_PATH: 'Scanner path',
    REASON_HONEYPOT: 'Honeypot',
    REASON_LISTED: 'Already listed',
}


def classify_bot_reason(path, user_agent, policy):
    if should_trap_path(path, policy):
        return REASON_PATH
    ua = (user_agent or '').strip()
    if not ua:
        return REASON_EMPTY_UA
    if is_bot_user_agent(user_agent, policy):
        return REASON_UA
    return REASON_LISTED


def honeypot_filled(post):
    if post is None:
        return False
    return bool((post.get(HONEYPOT_FIELD) or '').strip())
