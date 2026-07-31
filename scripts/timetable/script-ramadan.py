from datetime import datetime

import utils

fd = datetime(2026, 2, 18)
ld = datetime(2026, 3, 19)


def get_csv(t: int):
    import requests

    if t == 1:
        hlm = "4"
        acm = "1"
        file_name = "s.csv"
    elif t == 2:
        hlm = "3"
        acm = "2"
        file_name = "h.csv"
    else:
        exit()
    url = "https://downloads.salahtimes.com/api/prayerDownload"
    headers = {
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
    }

    params = {
        "format": "csv",
        "country": "uk",
        "place": "bristol",
        "hlm": hlm,
        "pcm": "5",
        "acm": acm,
        "ds": fd.strftime("%Y-%m-%d"),
        "de": ld.strftime("%Y-%m-%d"),
        "as24": "true",
    }

    response = requests.get(url, headers=headers, params=params)

    with open(file_name, "wb") as file:
        file.write(response.content)


def get_formatted_data():
    import pandas as pd

    # Read data from "s.csv" and "h.csv"
    s_data = pd.read_csv("s.csv")
    h_data = pd.read_csv("h.csv")
    # print(s_data)
    s_data.insert(loc=5, column="Asr Hanafi", value=h_data["Asar"])
    s_data = s_data.rename(columns={"Asar": "Asr Shafi"})
    x = s_data["Date"].str.split(" ", expand=True)[[0, 1]]
    s_data[["Date"]] = x[[1]]
    s_data.insert(loc=1, column="Day", value=x[[0]])
    s_data.insert(loc=0, column="Hijri", value=[x for x in range(1, 31)])
    s_data.insert(
        loc=10,
        column="Taraweeh",
        value=["19:20"] * 10 + ["19:40"] * 10 + ["20:00"] * 9 + ["N/A"],
    )
    return s_data


def gen_doc(df):
    from pylatex import Center, Command, Document, Figure, LineBreak, Tabular
    from pylatex.utils import NoEscape, bold

    # Create a LaTeX document
    geometry_options = {
        "tmargin": "0in",
        "lmargin": "0in",
        "bmargin": "0in",
        "rmargin": "0in",
    }
    doc = Document(geometry_options=geometry_options)
    doc.append(Command("pagenumbering", "gobble"))

    doc.preamble.append(NoEscape(r"\usepackage{graphicx}"))
    # doc.preamble.append(NoEscape(r"\usepackage[hidelinks]{hyperref}"))
    doc.preamble.append(NoEscape(r"\usepackage{hyperref}"))

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
        doc.append(NoEscape(r"\vspace{-30pt}"))
        doc.append(bold("Ramadan timetable"))
        doc.append(LineBreak())
        doc.append(NoEscape(r"\vspace{5pt}"))
        doc.append(bold(f"{fd.strftime('%a %d %b %Y')} - {ld.strftime('%a %d %b %Y')}"))
        doc.append(LineBreak())
        doc.append(NoEscape(r"\vspace{5pt}"))  # Inserting the vertical space
        doc.preamble.append(NoEscape(r"\setlength{\tabcolsep}{12pt}"))

        # Add a table to the document
        with doc.create(
            Tabular("|c|c|c|c|c|c|c|c|>{\columncolor[gray]{0.9}}c|c|c|", row_height=1.4)
        ) as table:
            table.add_hline()
            table.add_row(df.columns)
            # d = 1
            prev = "19:20"
            for i, row in df.iterrows():
                if i % 10 == 0:
                    table.add_hline()
                table.add_hline()
                c = None
                print(prev, row[10])
                if prev != row[10] and row[10] != "N/A":
                    prev = row[10]
                    row[10] = NoEscape(r"\cellcolor{gray}{%s}" % row[10])
                else:
                    prev = row[10]
                if row[2] == "Fri":
                    c = "lightgray"
                table.add_row(row, color=c)
            table.add_hline()

        doc.append(NoEscape(r"\vspace{5pt}"))  # Inserting the vertical space
        doc.append(LineBreak())
        t = utils.add_classes(
            Tabular("|c|", row_height=1.4),
            [
                utils.ClassRow(
                    "Jumuah prayer 13:00, UWE Centre for Sport, BS16 1ZL, open to Brothers and Sisters",
                    True,
                ),
                utils.ClassRow(
                    "Taraweeh - everyday - Enterprise 1, UWE Frenchay campus, BS34 8RB - open to brothers and sisters"
                ),
                utils.ClassRow(
                    "Iftars - every Monday, Wednesday and Saturday - EP1 - open to brothers and sisters - signup needed",
                ),
                utils.ClassRow(
                    "Fajr jamaa - everyday 25 minutes after athan - Brothers prayer room",
                ),
                utils.ClassRow(
                    "Quran circle - Saturdays at 15:30 - Ustadh Abu Malik - Brothers prayer room",
                ),
                utils.ClassRow(
                    "Roots - Wednesdays at 16:00 - Ustadh Abu Malik - Brothers and Sisters in 2X112",
                ),
            ],
        )
        doc.append(t)

        doc.append(LineBreak())
        doc.append(LineBreak())
        doc.append(bold("https://uwe.isoc.link/timetable"))
        doc.append(LineBreak())
        doc.append("Click or scan qr codes for details and forms")

    # Save the document to a PDF file
    doc.generate_pdf("prayer_time", clean_tex=False)


get_csv(1)
get_csv(2)

data = get_formatted_data()
data.to_csv("prayers.csv", index=False)

gen_doc(data)
