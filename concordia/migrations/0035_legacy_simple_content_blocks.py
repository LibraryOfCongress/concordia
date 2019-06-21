# flake8: noqa
from django.db import migrations


def load_legacy_content_blocks(apps, schema_editor):
    SimpleContentBlock = apps.get_model("concordia", "SimpleContentBlock")

    prototype_quicktips = SimpleContentBlock(
        label="prototype_quicktips", body=PROTOTYPE_QUICKTIPS
    )
    prototype_quicktips.full_clean()
    prototype_quicktips.save()

    classic_quicktips = SimpleContentBlock(
        label="classic_quicktips", body=CLASSIC_QUICKTIPS
    )
    classic_quicktips.full_clean()
    classic_quicktips.save()


class Migration(migrations.Migration):

    dependencies = [("concordia", "0034_auto_20190621_1223")]

    operations = [migrations.RunPython(load_legacy_content_blocks)]


PROTOTYPE_QUICKTIPS = """
<h2 class="sr-only">Help</h2>
<section>
    <h3>Transcription tips</h3>
    <ul>
        <li>Type what you see: Preserve line breaks, original spelling, and punctuation.</li>
        <li>Use brackets [ ] around deleted, illegible or partially legible text.</li>
        <li>Use question mark ? for any words or letters you can't identify.</li>
        <li>Use square brackets and asterisks [ * * ] around text from margins.</li>
        <li>Include insertions where you would read them in the text.</li>
        <li>Click “Save” to save work in progress and “Submit” when complete</li>
    </ul>
</section>
<hr />
<section>
    <h3>Review tips</h3>
    <ul>
        <li>Carefully compare each line of the transcription to the original.</li>
        <li>Use “Transcription tips” as a guide.</li>
        <li>Click “Accept” if accurate or “Edit” if page needs correction.</li>
    </ul>
</section>
<hr />
<section>
    <h3 class="sr-only">More information</h3>
    <p>
    Find more detailed instructions in the <a href="/help-center/" target="_blank">Help Center</a>
    </p>
</section>
<hr />
<section>
    <h3>Keyboard Shortcuts</h3>
    <ul class="list-unstyled d-table">
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>w</kbd> or <kbd>up</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2 w-60">Scroll the viewport up</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>s</kbd> or <kbd>down</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Scroll the viewport down</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>a</kbd> or <kbd>left</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Scroll the viewport left</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>d</kbd> or <kbd>right</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Scroll the viewport right</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>0</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Fit the entire image to the viewport</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>-</kbd> or <kbd>_</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Zoom the viewport out</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>=</kbd> or <kbd>+</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Zoom the viewport in</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>r</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Rotate the viewport clockwise</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>R</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Rotate the viewport counterclockwise</div>
        </li>
        <li class="d-table-row">
            <div class="d-table-cell align-middle border-top py-2"><kbd>f</kbd></div>
            <div class="d-table-cell align-middle border-top py-2 pl-2">Flip the viewport horizontally</div>
        </li>
    </ul>
</section>
"""

CLASSIC_QUICKTIPS = """
<ul>
    <li>Transcribe original spelling, punctuation, word order, and any page numbers or catalog marks.</li>
    <li>Preserve line breaks except when a word breaks over a line or page. Then transcribe it on the line or page where it starts.</li>
    <li>Use brackets [ ] around deleted, illegible or partially legible text, and square brackets and asterisks around text in margins [ * * ].</li>
    <li>Transcribe any words or letters you can't identify as [?].</li>
    <li>Include insertions where you would read them in the text.</li>
</ul>
Find more detailed instructions in the <a href="/help-center/">Help Center</a>
"""
