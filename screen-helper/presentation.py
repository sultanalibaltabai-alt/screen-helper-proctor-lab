"""Minimal overlay output; diagnostics contain no recognized questions or answer history."""


def result_kind(answer):
    if answer.startswith('Запрос отменён'):
        return 'cancelled'
    if answer.startswith(('API:', 'Capture', 'Config:')):
        return 'error'
    return 'answer'


def result_text(answer):
    kind = result_kind(answer)
    return '' if kind == 'cancelled' else '?' if kind == 'error' else answer


def result_report(answer, metrics, seconds):
    allowed = ('http_status', 'model_used', 'model_returned', 'cache_hit', 'deadline_exceeded',
               'network_error_type', 'image_bytes', 'capture_seconds', 'encoding_seconds',
               'input_tokens', 'output_tokens', 'total_tokens', 'validation_seconds')
    return {'version': '8.5', 'result_kind': result_kind(answer),
            'error': answer if result_kind(answer) == 'error' else None,
            'metrics': {k: metrics[k] for k in allowed if k in metrics},
            'seconds': round(seconds, 2), 'desktop_saved': False, 'answer_saved': False}
