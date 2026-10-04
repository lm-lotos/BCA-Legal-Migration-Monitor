import difflib
import html

def render_diff(old_text, new_text):
    old_words = old_text.split()
    new_words = new_text.split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words)

    old_parts = []
    new_parts = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_chunk = " ".join(old_words[i1:i2])
        new_chunk = " ".join(new_words[j1:j2])
        if tag == "equal":
            old_parts.append(html.escape(old_chunk))
            new_parts.append(html.escape(new_chunk))

        elif tag == "delete":
            old_parts.append(
                f'<span class="diff-old">{html.escape(old_chunk)}</span>'
            )

        elif tag == "insert":
            new_parts.append(
                f'<span class="diff-new">{html.escape(new_chunk)}</span>'
            )
        elif tag == "replace":
            old_parts.append(
                f'<span class="diff-old">{html.escape(old_chunk)}</span>'
            )
            new_parts.append(
                f'<span class="diff-new">{html.escape(new_chunk)}</span>'
            )

    return " ".join(old_parts), " ".join(new_parts)

DIFF_CSS = """
<style>
.diff-old {
    background-color: #fde2e2;
    color: #777777;
    text-decoration: line-through;
    padding: 2px 4px;
    border-radius: 4px;
}

.diff-new {
    background-color: #dcfce7;
    color: #1f2937;
    padding: 2px 4px;
    border-radius: 4px;
}
</style>
"""
        