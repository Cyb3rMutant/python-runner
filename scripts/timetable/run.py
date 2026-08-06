import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from pylatex import Center, Command, Document, LineBreak, Tabular
from pylatex.utils import NoEscape, bold

from . import utils

ASSETS_DIR = Path(__file__).resolve().parent


def date_range():
    today = datetime.now() - timedelta(days=20)
    next_month = today.month % 12 + 1
    next_year = today.year + (today.month // 12)
    fd = datetime(next_year, next_month, 1)

    next_next_month = (today.month + 1) % 12
    next_next_year = today.year + ((today.month + 1) // 12)
    ld = datetime(next_next_year, next_month + 1, 1) - timedelta(days=1)
    return fd, ld


def gen_doc(df, fd, ld):
    geometry_options = {
        "tmargin": "0in",
        "lmargin": "0in",
        "bmargin": "0in",
        "rmargin": "0in",
    }
    doc = Document(geometry_options=geometry_options, font_size="large")
    doc.append(Command("pagenumbering", "gobble"))

    doc.preamble.append(NoEscape(r"\usepackage{graphicx}"))
    doc.preamble.append(NoEscape(r"\usepackage{hyperref}"))
    # Images live alongside this script, not in the compile cwd, so point
    # LaTeX at them explicitly instead of changing every \includegraphics call.
    doc.preamble.append(NoEscape(r"\graphicspath{{" + str(ASSETS_DIR) + r"/}}"))

    doc.append(NoEscape(r"""
    \noindent
    \begin{minipage}[t]{0.33\textwidth}
        \raggedright
        \href{https://uwe.isoc.link/timetable-left-link}{
            \includegraphics[width=100px]{left-with-text.png}
        }
    \end{minipage}
    \begin{minipage}[t]{0.33\textwidth}
        \centering
        \includegraphics[width=100px]{logo.png}
    \end{minipage}
    \begin{minipage}[t]{0.33\textwidth}
        \raggedleft
        \href{https://uwe.isoc.link/timetable-right-link}{
            \includegraphics[width=100px]{right-with-text.png}
        }
    \end{minipage}

    \vspace{1cm}
    """))

    with doc.create(Center()):
        doc.append(NoEscape(r"\vspace{-40pt}"))
        doc.append(bold(f"{fd.strftime('%a %d %b %Y')} - {ld.strftime('%a %d %b %Y')}"))
        doc.append(LineBreak())

        doc.preamble.append(NoEscape(r"\setlength{\tabcolsep}{12pt}"))
        with doc.create(Tabular("|c|c|c|c|c|c|c|c|c|", row_height=1.35)) as table:
            table.add_hline()
            table.add_row(df.columns)
            table.add_hline()
            for _, row in df.iterrows():
                table.add_hline()
                c = None
                if row.iloc[1] == "Fri":
                    c = "lightgray"
                table.add_row(row, color=c)
            table.add_hline()

        doc.append(LineBreak())
        t = utils.add_classes(
            Tabular("|c|", row_height=1.4),
            [
                utils.ClassRow(
                    "Jumuah prayer 13:00, UWE Centre for Sport, BS16 1ZL, open to Brothers and Sisters",
                    True,
                ),
                utils.ClassRow("ALL CLASSES PAUSED UNTIL FAURTHER NOTICE"),
            ],
        )

        doc.append(t)
        doc.append(LineBreak())
        doc.append(LineBreak())
        doc.append(bold("https://uwe.isoc.link/timetable"))

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "prayer_time"
        doc.generate_pdf(str(pdf_path), clean_tex=True)
        return pdf_path.with_suffix(".pdf").read_bytes()


def run():
    fd, ld = date_range()

    data = utils.timetable_data(fd, ld)

    pdf_bytes = gen_doc(data, fd, ld)

    return pdf_bytes, "pdf"
