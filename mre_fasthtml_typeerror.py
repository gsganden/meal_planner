import html

import fasthtml.common as fh

# FastHTML app setup
# Use FastHTMLWithLiveReload to be closer to the main app's setup
app = fh.FastHTMLWithLiveReload()
rt = app.route


@rt("/")
async def get_main_page():
    """Serves the main page with buttons to trigger swaps."""
    return fh.Html(
        fh.Head(
            fh.Title("MRE FastHTML TypeError"),
            fh.Script(src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"),
            fh.Style("""
                body { font-family: sans-serif; padding: 20px; }
                button { margin-right: 10px; padding: 8px 12px; }
                #target-div { margin-top: 20px; border: 1px solid #ccc; padding: 10px; min-height: 50px; }
            """),
        ),
        fh.Body(
            fh.H1("MRE for FastHTML TypeError"),
            fh.P(
                "Click the 'Trigger Problematic Swap' button. "
                "If the TypeError occurs, the content in the target div below "
                "will not update as expected, and an error should be logged "
                "in the server console."
            ),
            fh.P(
                "Click the 'Trigger Working Swap' button to see the "
                "workaround using fh.NotStr."
            ),
            fh.Button(
                "Trigger Problematic Swap",
                hx_post="/swap-problem",
                hx_target="#target-div",
                hx_swap="innerHTML",  # Key: innerHTML swap for a multi-component return
            ),
            fh.Button(
                "Trigger Working Swap (with NotStr)",
                hx_post="/swap-working",
                hx_target="#target-div",
                hx_swap="innerHTML",
            ),
            fh.Div("Initial content in target-div.", id="target-div"),
        ),
    )


@rt("/swap-problem", methods=["POST"])
async def post_swap_problem():
    """
    This route attempts to return a structure that caused TypeErrors.
    This version tries to closely mimic the structure from the main app's
    _build_diff_content_children function when it was returning components.
    """
    # Replicate styles and classes from the main app
    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"
    base_classes = (
        "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 overflow-auto text-xs"
    )

    # Create content with Del/Ins for the Pre tags
    before_pre_children = [
        "Original Line 1\n",
        fh.Del("Original Line 2 (deleted)\n"),
        "Original Line 3\n",
    ]
    after_pre_children = [
        "Current Line 1\n",
        fh.Ins("Current Line 2 (inserted)\n"),
        "Current Line 3\n",
    ]

    # Build the first Div (mimicking before_area_div)
    div1 = fh.Div(
        fh.Strong("MRE Before Diff"),
        fh.Pre(
            *before_pre_children,
            id="mre-diff-before-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls="w-1/2",  # Simplified class, could add more if needed
    )

    # Build the second Div (mimicking after_area_div)
    div2 = fh.Div(
        fh.Strong("MRE After Diff"),
        fh.Pre(
            *after_pre_children,
            id="mre-diff-after-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls="w-1/2",  # Simplified class
    )

    return fh.Group(div1, div2)


@rt("/swap-working", methods=["POST"])
async def post_swap_working():
    """
    This route demonstrates the workaround by manually rendering FT components
    to strings and using fh.NotStr.
    """
    # Content for fh.Del and fh.Ins is typically a simple string.
    # html.escape is important if children could be arbitrary user input.
    deleted_text = "This is deleted text."
    inserted_text = "This is inserted text."

    # Manually create the HTML string, similar to what working FT rendering would do.
    # The children of Del/Ins are already strings here.
    del_html = f"<del>{html.escape(deleted_text)}</del>"
    ins_html = f"<ins>{html.escape(inserted_text)}</ins>"

    final_html_string = f"""
    <div>
        <h3>Working Update (NotStr):</h3>
        <pre>Item 1: {del_html}<br/>Item 2: {ins_html}</pre>
    </div>
    """
    return fh.NotStr(final_html_string)


# How to run this MRE:
# 1. Save this file as `mre_fasthtml_typeerror.py`.
# 2. Make sure you have `fasthtml` and `uvicorn` installed in your environment:
#    (uvicorn is used internally by app.serve())
#    `pip install fasthtml uvicorn`
# 3. Run the script directly from your terminal:
#    `python mre_fasthtml_typeerror.py`
#    FastHTML will typically pick a port like 8000 or the next available one.
#    Check your console output for the exact URL (e.g., http://127.0.0.1:8000).
# 4. Open your web browser and navigate to the URL shown in your console.
# 5. Click the "Trigger Problematic Swap" button.
#    - Observe if the content in the "target-div" updates correctly.
#    - Check the server console (where you ran Uvicorn) for a
#      `TypeError: __str__ returned non-string (type FT)` or similar.
# 6. Click the "Trigger Working Swap (with NotStr)" button.
#    - Observe that the content updates correctly using the workaround.

# To run using FastHTML's built-in serve:
if __name__ == "__main__":
    fh.serve()
