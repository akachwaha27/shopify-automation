# Content plan (Ashvara)

`plan.csv` is the sheet: **one row = one product video**. Rows are written by a Claude scheduled task (or by
hand) following `voice.md`. At ~10:17 AM ET the bot sends the Ready rows to Telegram (marked 📋); tap the
numbers to make them, or ignore it and it makes the top ones itself.

Every product video uses the store's own photos on every 2nd scene and on the last scene (with the live price
and the product link), and matching stock clips in between. The product must be **Active** in Shopify; if a
row's `product` handle isn't live, the bot skips it and tells you.

`status.json` tracks each row: Ready → Sent → Making → Preview → Published (or Not picked / Skipped / Failed).
Your PC copy is the "Content Plan" tab in `Ashvara Shorts Library.xlsx` (see `tools/sync_library.py`).

To add a row by hand: copy an existing row, give it a new `id` (P<date>-<nn>), change the title, hook, script,
footage and `product` handle. Keep `format` = `product`.
