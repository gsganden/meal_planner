import fasthtml.common as fh
import monsterui.all as mu

app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route


def sidebar():
    nav = mu.NavContainer(
        fh.Li(
            fh.A(
                mu.DivFullySpaced("Home"),
                href="/",
                hx_target="#content",
                hx_push_url="true",
            )
        ),
        mu.NavParentLi(
            fh.A(mu.DivFullySpaced("Recipes")),
            mu.NavContainer(
                fh.Li(
                    fh.A(
                        "Extract",
                        href="/recipes/extract",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                parent=False,
            ),
        ),
        uk_nav=True,
        cls=mu.NavT.primary,
    )
    return fh.Div(nav, cls="space-y-4 p-4 w-full md:w-full")


def with_layout(content):
    return fh.Title("Meal Planner"), fh.Div(cls="flex flex-col md:flex-row w-full")(
        fh.Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
        fh.Div(content, cls="md:w-4/5 w-full p-4", id="content"),
    )


@rt("/")
def get():
    main_content = mu.Titled("Home")
    return with_layout(main_content)


@rt("/recipes/extract")
def recipes_extract():
    url_input = mu.Input(
        id="recipe_url", name="recipe_url", type="url", placeholder="Enter Recipe URL"
    )
    submit_button = mu.Button("Extract Recipe")
    initial_form = mu.Form(
        url_input,
        submit_button,
        hx_post="/extract",
        hx_target="#content",
        hx_swap="innerHTML",
    )
    return with_layout(mu.Titled("Extract Recipe", fh.Div(initial_form, id="content")))


fh.serve()
