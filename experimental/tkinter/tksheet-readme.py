from tksheet import (
    Sheet,
    num2alpha as n2a,
)
import tkinter as tk


class demo(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.frame = tk.Frame(self)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)
        self.sheet = Sheet(
            self.frame,
            empty_horizontal=0,
            empty_vertical=0,
            paste_can_expand_x=True,
            paste_can_expand_y=True,
            align="w",
            header_align="c",
            data=[[f"Row {r}, Column {c}\nnewline 1\nnewline 2" for c in range(6)] for r in range(21)],
            headers=[
                "Dropdown Column",
                "Checkbox Column",
                "Center Aligned Column",
                "East Aligned Column",
                "",
                "",
            ],
            theme="dark",
            height=520,
            width=930,
        )
        self.sheet.enable_bindings("all", "edit_index", "edit_header")
        self.sheet.popup_menu_add_command(
            "Hide Rows",
            self.hide_rows,
            table_menu=False,
            header_menu=False,
            empty_space_menu=False,
        )
        self.sheet.popup_menu_add_command(
            "Show All Rows",
            self.show_rows,
            table_menu=False,
            header_menu=False,
            empty_space_menu=False,
        )
        self.sheet.popup_menu_add_command(
            "Hide Columns",
            self.hide_columns,
            table_menu=False,
            index_menu=False,
            empty_space_menu=False,
        )
        self.sheet.popup_menu_add_command(
            "Show All Columns",
            self.show_columns,
            table_menu=False,
            index_menu=False,
            empty_space_menu=False,
        )
        self.frame.grid(row=0, column=0, sticky="nswe")
        self.sheet.grid(row=0, column=0, sticky="nswe")
        colors = (
            "#509f56",
            "#64a85b",
            "#78b160",
            "#8cba66",
            "#a0c36c",
            "#b4cc71",
            "#c8d576",
            "#dcde7c",
            "#f0e782",
            "#ffec87",
            "#ffe182",
            "#ffdc7d",
            "#ffd77b",
            "#ffc873",
            "#ffb469",
            "#fea05f",
            "#fc8c55",
            "#fb784b",
            "#fa6441",
            "#f85037",
        )
        self.sheet.align_columns(columns=2, align="c")
        self.sheet.align_columns(columns=3, align="e")
        self.sheet.create_index_dropdown(r=0, values=["Dropdown"] + [f"{i}" for i in range(15)])
        self.sheet.create_index_checkbox(r=3, checked=True, text="Checkbox")
        self.sheet.create_dropdown(r="all", c=0, values=["Dropdown"] + [f"{i}" for i in range(15)])
        self.sheet.create_checkbox(r="all", c=1, checked=True, text="Checkbox")
        self.sheet.create_header_dropdown(c=0, values=["Header Dropdown"] + [f"{i}" for i in range(15)])
        self.sheet.create_header_checkbox(c=1, checked=True, text="Header Checkbox")
        self.sheet.align_cells(5, 0, align="c")
        self.sheet.highlight_cells(5, 0, bg="gray50", fg="blue")
        self.sheet.highlight_cells(17, canvas="index", bg="yellow", fg="black")
        self.sheet.highlight_cells(12, 1, bg="gray90", fg="purple")
        for r in range(len(colors)):
            self.sheet.highlight_cells(row=r, column=3, fg=colors[r])
            self.sheet.highlight_cells(row=r, column=4, bg=colors[r], fg="black")
            self.sheet.highlight_cells(row=r, column=5, bg=colors[r], fg="purple")
        self.sheet.highlight_cells(column=5, canvas="header", bg="white", fg="purple")
        self.sheet.align(n2a(2), align="c")
        self.sheet.align(n2a(3), align="e")
        self.sheet.dropdown(
            self.sheet.span("A", header=True),
            values=["Dropdown"] + [f"{i}" for i in range(15)],
        )
        self.sheet.checkbox(
            self.sheet.span("B", header=True),
            checked=True,
            text="Checkbox",
        )
        self.sheet.align(5, 0, align="c")
        self.sheet.highlight(5, 0, bg="gray50", fg="blue")
        self.sheet.highlight(
            self.sheet.span(17, index=True, table=False),
            bg="yellow",
            fg="black",
        )
        self.sheet.highlight(12, 1, bg="gray90", fg="purple")
        for r in range(len(colors)):
            self.sheet.highlight(r, 3, fg=colors[r])
            self.sheet.highlight(r, 4, bg=colors[r], fg="black")
            self.sheet.highlight(r, 5, bg=colors[r], fg="purple")
        self.sheet.highlight(
            self.sheet.span(n2a(5), header=True, table=False),
            bg="white",
            fg="purple",
        )
        self.sheet.set_all_column_widths()
        self.sheet.extra_bindings("all", self.all_extra_bindings)

    def hide_rows(self, event=None):
        rows = self.sheet.get_selected_rows()
        if rows:
            self.sheet.hide_rows(rows)

    def show_rows(self, event=None):
        self.sheet.display_rows("all", redraw=True)

    def hide_columns(self, event=None):
        columns = self.sheet.get_selected_columns()
        if columns:
            self.sheet.hide_columns(columns)

    def show_columns(self, event=None):
        self.sheet.display_columns("all", redraw=True)

    def all_extra_bindings(self, event=None):
        return event.value


app = demo()
app.mainloop()