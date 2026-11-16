# Wine database

This project keeps the original Excel export safe while creating a cleaner working database for searching and analysis.

## The three files

- `input_file.csv` is the direct export from Excel. The program only reads it; never edit it through this project.
- `wine_database.csv` is the working database. It contains every original column plus clean versions of selected fields.
- `cleaning_rules.csv` remembers decisions such as a spelling correction, so they are applied consistently to future imports.

## How it works

Run the importer whenever you export a newer `input_file.csv`:

```sh
python3 wine_manager.py import
```

Completely empty trailing rows from the Excel export are ignored. Every other source row must have a unique ID. A new ID creates a new row in `wine_database.csv`; an existing ID updates the original source columns in its existing row. This means that a review, price, date, or any other later addition in Excel reaches the working database on the next import.

The original value is always retained. For example, `Grape/Vine` remains the value from Excel, while `grapes_clean` provides an alphabetically sorted pipe-separated list such as `Chardonnay | Pinot Noir`. Numbers and proportions are intentionally left in the original field and omitted from the analysis list: `100% Montepulciano` becomes `Montepulciano`, and `1/2 Terret, 1/2 Riesling` becomes `Riesling | Terret`.

## Reviewing suspicious values

Start with grapes:

```sh
python3 wine_manager.py review grape
```

The program presents rare, unreviewed values (one or two occurrences), one at a time, with nearby spellings where it finds them. For grapes, it automatically reviews a reordered or punctuation-only variant when every grape in its normalized list has already been approved. It only asks you about a normalized grape list when it contains at least one grape name not yet approved. At each prompt you can:

- Press **Enter** to keep the displayed value (for grapes, it is converted into an alphabetically sorted list).
- Enter a **number** to use a displayed suggestion. Grape suggestions are based on the individual grape currently being checked, rather than an unrelated whole blend.
- Type replacement text to save your own wording. For a blend, enter its grape names naturally, for example `Terret, Riesling`; the program displays the resulting sorted grape list before saving.
- Enter **`s`** to skip just that value and return to it in a later review.
- Enter **`q`** or press **Ctrl-D** to end the current review. Earlier decisions are already saved.

For grapes, the review prompt first shows the normalized blend, then explains why it stopped for review, and asks only about each unapproved grape in that blend. The approved grapes stay in place automatically. It checks each newly reviewed grape for uncommon values, then shows the reconstructed list for a final save confirmation. It shows the analysis value rather than proportion notation: for example, `100% Pecorino` is shown as `Pecorino`. The original source value is retained in `wine_database.csv` and is never changed.

Before saving a grape list, the program checks each newly reviewed grape that occurs in only one or two rows and requires an explicit `y` confirmation. It then shows the complete list on its own lines and asks for confirmation.

At the end of every review, a short summary reports how many decisions were saved, kept, corrected from a suggestion, typed manually, or skipped. Choosing `s` or declining either grape confirmation counts as skipped for later.

## Full audit for repeated values

The normal review deliberately focuses on values that appear once or twice. To check every unreviewed spelling—including a repeated typo such as `Chardonay` appearing 55 times—run:

```sh
python3 wine_manager.py review grape --all
```

Full audit lists frequent values first. Saving `Chardonay` as `Chardonnay` updates every matching current row and stores that rule for future imports. Later grape reviews offer up to three likely approved grape-name corrections for the specific component being checked. A decision made earlier in the same review session becomes available immediately.

Repeat with:

```sh
python3 wine_manager.py review producer
python3 wine_manager.py review appellation
```

Each confirmed choice is stored in `cleaning_rules.csv`. The next import uses it automatically. If you change a controlled source value, such as `Grape/Vine`, its clean value is refreshed and marked `pending` unless an existing rule covers the new wording or all grapes in its normalized list are already approved. A change to an unrelated field, such as `Review`, does not disturb prior cleaning decisions.

## Columns added to the working database

- `_record_key`: internal duplicate-protection key; ID-based where possible.
- `grapes_clean`, `producer_clean`, `appellation_clean`: values intended for analysis.
- the matching `*_status` fields: `pending`, `reviewed`, or `empty`.

## Intended workflow

1. Export Excel as `input_file.csv`.
2. Run `import`.
3. Review newly suspicious values when convenient.
4. Use `wine_database.csv` for analysis, filters, and eventually as the editable main file if that still feels right.

This first version deliberately does not change existing source values automatically. We can expand the review criteria after seeing how its first pass feels—for example, country codes, dates, colours, price formats, or grape-name standards.
