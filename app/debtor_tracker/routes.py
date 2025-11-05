import os
import pandas as pd
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from flask_login import login_required, current_user
from app.decorators import permission_required
from app.utils import log_activity
import io
import re
import pdfplumber
import numpy as np

# --- UTWORZENIE MODUŁU (BLUEPRINT) ---
bp = Blueprint('debtor_tracker', __name__, template_folder='templates', url_prefix='/debtor_tracker')

# --- Konfiguracja CSV (Wpłaty) ---
# (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
CSV_ORIGINAL_HEADERS = [
    "DataKsiegowania", "DataWaluty", "TytulPrzelewu", "NadawcaInfo",
    "NrKontaNadawcy", "KwotaPrzelewu", "SaldoPoOperacji", "IDTransakcji",
    "_PustaKolumna"
]
CSV_COLUMNS_TO_KEEP = ["DataKsiegowania", "DataWaluty", "TytulPrzelewu", "NadawcaInfo", "KwotaPrzelewu"]
CSV_DISPLAY_NAMES = {
    "DataKsiegowania": "Data Księgowania", "DataWaluty": "Data Waluty",
    "TytulPrzelewu": "Tytuł Przelewu (Wpłata)", "NadawcaInfo": "Od Kogo (Wpłata)",
    "KwotaPrzelewu": "Kwota Wpłaty"
}
CSV_DELIMITER = ','
CSV_ENCODING = 'utf-8' # lub 'cp1250', 'iso-8859-2'
CSV_DECIMAL = ','

# --- Konfiguracja PDF (Faktury) ---
# (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
PDF_ROW_PATTERN = re.compile(
    r"^\s*\d+\.\s+"                 # 1. Numer porządkowy
    r"([A-Z]+\s+[\w/.-]+)\s+"      # (1) Typ+Numer dokumentu
    r"(?:[A-Z0-9]+)\s+"               # (IGNOROWANE) Numer zamówienia
    r"(.+?)\s+"                       # (2) Kontrahent
    r"(\d{4}-\d{2}-\d{2})\s+"      # (3) Data wystawienia
    r"(\d{4}-\d{2}-\d{2})\s+"      # (4) Termin zapłaty
    r"([\d\s.,]+?)\s+PLN\s+"         # (5) Wartość netto
    r"([\d\s.,]+?)\s+PLN"            # (6) Wartość brutto
    r"\s*$",
    re.MULTILINE | re.IGNORECASE
)

# --- Konfiguracja Ogólna ---
# (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
ALLOWED_EXTENSIONS = {'csv', 'pdf'}
AMOUNT_TOLERANCE = 0.01 # Tolerancja dla porównywania kwot float

# --- Funkcje pomocnicze (kopiujemy je z Twojego app.py) ---

def allowed_file(filename):
    """Sprawdza dozwolone rozszerzenia."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_invoice_from_payment_title(title):
    """Próbuje wyciągnąć numer faktury z tytułu WPŁATY (z CSV)."""
    if not isinstance(title, str): return ""
    patterns = [
        r'(?:FV|PA|FAK|Faktura|Zamówienie|Zam)\s*(?:nr\.?|numer)?\s*([\w/.-]+)',
        r'REF:\s*([\w/.-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match: return match.group(1).strip()
    if re.fullmatch(r'[A-Z0-9/.-]+', title) and len(title) > 4 and ' ' not in title:
         return title
    return ""

def parse_pdf_invoices(pdf_stream):
    """Próbuje wyciągnąć dane faktur (Nr, Kwota Brutto, Kontrahent) z PDF i odfiltrowuje 'PA'."""
    invoices_data = []
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            full_text = ""
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    full_text += page_text + "\n"
                # else: print(f"Ostrzeżenie: Strona {i+1} PDF nie zawierała tekstu.")

            print("  -> Rozpoczynanie parsowania tekstu PDF (wzorzec wiersza)...")
            matches = PDF_ROW_PATTERN.finditer(full_text)
            count = 0
            parsed_count = 0
            for match in matches:
                count += 1
                try:
                    invoice_number = match.group(1).strip()
                    if invoice_number.startswith('PA '): continue # Filtruj PA
                    kontrahent = match.group(2).strip()
                    brutto_str = match.group(6).strip()
                    amount_str_normalized = brutto_str.replace(' ', '').replace(',', '.')
                    amount = round(float(amount_str_normalized), 2)
                    invoices_data.append({
                        'NrFakturyPDF': invoice_number, 'KontrahentPDF': kontrahent, 'KwotaPDF': amount
                    })
                    parsed_count += 1
                except (ValueError, IndexError) as e:
                    print(f"    Ostrzeżenie podczas parsowania wiersza PDF ({e}): Nr='{match.group(1).strip() if match.group(1) else '?'}' KwotaStr='{match.group(6).strip() if match.group(6) else '?'}'")

            print(f"  -> Zakończono parsowanie. Znaleziono {count} wierszy pasujących. Sparowano poprawnie {parsed_count} faktur (poza PA).")

            df_temp = pd.DataFrame(invoices_data)

    except Exception as pdf_err:
         print(f"  Krytyczny błąd podczas przetwarzania PDF: {pdf_err}")
         import traceback; traceback.print_exc()
         return pd.DataFrame()

    return df_temp

# --- GŁÓWNE TRASY MODUŁU (ZABEZPIECZONE) ---

@bp.route('/', methods=['GET'])
@login_required
@permission_required('admin')
def index():
    """Wyświetla formularz do wysłania obu plików."""
    return render_template('upload_dual.html')

@bp.route('/process', methods=['POST'])
@login_required
@permission_required('admin')
def process_files():
    """Odbiera pliki CSV i PDF, przetwarza i porównuje."""
    # --- Walidacja i odbiór plików ---
    if 'csv_file' not in request.files:
        flash('Proszę wybrać plik CSV!', 'error')
        return redirect(url_for('.index')) # ZMIANA: .index
    csv_file = request.files['csv_file']
    if csv_file.filename == '':
        flash('Proszę wybrać plik CSV!', 'warning')
        return redirect(url_for('.index')) # ZMIANA: .index
    if not allowed_file(csv_file.filename):
        flash('Nieprawidłowy plik CSV.', 'error')
        return redirect(url_for('.index')) # ZMIANA: .index

    if 'pdf_files' not in request.files:
         flash('Proszę wybrać plik(i) PDF!', 'error')
         return redirect(url_for('.index')) # ZMIANA: .index
    pdf_files = request.files.getlist('pdf_files')
    if not pdf_files or all(f.filename == '' for f in pdf_files):
        flash('Proszę wybrać przynajmniej jeden plik PDF!', 'warning')
        return redirect(url_for('.index')) # ZMIANA: .index

    df_payments = pd.DataFrame()
    all_invoices_dfs = []
    processed_pdf_filenames = []

    # --- Odczyt CSV ---
    try:
        print(f"Rozpoczynanie odczytu CSV: {csv_file.filename}")
        stream_csv = io.StringIO(csv_file.stream.read().decode(CSV_ENCODING), newline=None)
        df_payments = pd.read_csv(
            stream_csv, delimiter=CSV_DELIMITER, header=None, names=CSV_ORIGINAL_HEADERS,
            decimal=CSV_DECIMAL, skipinitialspace=True, on_bad_lines='warn'
        )
        df_payments['KwotaPrzelewu'] = pd.to_numeric(df_payments['KwotaPrzelewu'], errors='coerce')
        rows_before = len(df_payments)
        df_payments.dropna(subset=['KwotaPrzelewu'], inplace=True)
        rows_after = len(df_payments)
        if rows_before > rows_after: print(f"Ostrzeżenie: Usunięto {rows_before - rows_after} wierszy z CSV z powodu błędu kwoty.")
        df_payments = df_payments[CSV_COLUMNS_TO_KEEP].copy()
        df_payments = df_payments.rename(columns=CSV_DISPLAY_NAMES)
        df_payments['NrFaktury_z_Tytulu'] = df_payments['Tytuł Przelewu (Wpłata)'].apply(extract_invoice_from_payment_title)
        print(f"Wczytano {len(df_payments)} poprawnych wpłat z CSV.")
    except Exception as e:
        flash(f"Błąd podczas odczytu pliku CSV '{csv_file.filename}': {e}", 'error')
        import traceback; traceback.print_exc()
        return redirect(url_for('.index')) # ZMIANA: .index

    # --- Odczyt wielu PDFów ---
    # (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
    for pdf_file_storage in pdf_files:
        if pdf_file_storage and allowed_file(pdf_file_storage.filename):
            filename = pdf_file_storage.filename
            print(f"\nRozpoczynanie przetwarzania PDF: {filename}")
            try:
                df_single_pdf = parse_pdf_invoices(pdf_file_storage.stream)
                if not df_single_pdf.empty:
                    df_single_pdf['KwotaPDF'] = pd.to_numeric(df_single_pdf['KwotaPDF'], errors='coerce')
                    df_single_pdf.dropna(subset=['KwotaPDF'], inplace=True)
                    if not df_single_pdf.empty:
                        all_invoices_dfs.append(df_single_pdf)
                        processed_pdf_filenames.append(filename)
                        print(f"-> Przetworzono {len(df_single_pdf)} faktur (poza PA) z pliku {filename}.")
            except Exception as e:
                flash(f"Wystąpił błąd podczas przetwarzania pliku PDF '{filename}': {e}. Pomijanie.", 'warning')
                print(f"Błąd przetwarzania PDF {filename}: {e}")
                import traceback; traceback.print_exc()
        else:
             flash(f'Pominięto plik "{pdf_file_storage.filename}" - nieprawidłowy typ.', 'warning')

    # --- Agregacja danych PDF ---
    # (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
    if not all_invoices_dfs:
        df_invoices = pd.DataFrame(columns=['NrFakturyPDF', 'KontrahentPDF', 'KwotaPDF'])
        print("Nie udało się przetworzyć żadnych danych z plików PDF.")
    else:
        df_invoices = pd.concat(all_invoices_dfs, ignore_index=True)
        print(f"\nPołączono dane z {len(processed_pdf_filenames)} plików PDF. Łącznie {len(df_invoices)} faktur (poza PA).")
        if 'NrFakturyPDF' in df_invoices.columns:
            invoices_before_dedup = len(df_invoices)
            df_invoices['NrFakturyPDF'] = df_invoices['NrFakturyPDF'].astype(str)
            df_invoices = df_invoices.drop_duplicates(subset=['NrFakturyPDF'], keep='first')
            invoices_after_dedup = len(df_invoices)
            if invoices_before_dedup > invoices_after_dedup:
                print(f"Usunięto {invoices_before_dedup - invoices_after_dedup} zduplikowanych faktur (wg numeru).")

    # --- Porównanie Danych ---
    # (Ta sekcja pozostaje bez zmian - kopiujemy ją z Twojego app.py)
    if df_payments.empty and df_invoices.empty:
         flash("Brak poprawnych danych w obu plikach.", "warning")
         return redirect(url_for('.index')) # ZMIANA: .index

    # Przygotuj kolumny nawet jeśli jedna ramka jest pusta
    if not df_payments.empty:
        df_payments['Kwota_MergeKey'] = df_payments['Kwota Wpłaty'].round(2)
        df_payments = df_payments.reset_index(drop=True)
        df_payments['NrFaktury_z_Tytulu_Upper'] = df_payments['NrFaktury_z_Tytulu'].astype(str).str.strip().str.upper()
    else:
        df_payments = pd.DataFrame(columns=list(CSV_DISPLAY_NAMES.values()) + ['NrFaktury_z_Tytulu', 'Kwota_MergeKey', 'Payment_ID', 'NrFaktury_z_Tytulu_Upper'])

    if not df_invoices.empty:
        df_invoices['Kwota_MergeKey'] = df_invoices['KwotaPDF'].round(2)
        df_invoices = df_invoices.reset_index(drop=True)
        df_invoices['NrFakturyPDF_Upper'] = df_invoices['NrFakturyPDF'].astype(str).str.strip().str.upper()
        if 'KontrahentPDF' not in df_invoices.columns: df_invoices['KontrahentPDF'] = '-'
        df_invoices['KontrahentPDF'] = df_invoices['KontrahentPDF'].fillna('-')
    else:
        df_invoices = pd.DataFrame(columns=['NrFakturyPDF', 'KontrahentPDF', 'KwotaPDF', 'Kwota_MergeKey', 'Invoice_ID', 'NrFakturyPDF_Upper'])

    # (Cała reszta logiki porównania, analizy statusu, podziału na sekcje,
    # obliczania sum, oznaczania powtarzających się kontrahentów,
    # sortowania i podsumowania dłużników pozostaje bez zmian.
    # Kopiujemy ją 1:1 z Twojego app.py, aż do `return render_template`)
    
    # ... (logika od try: print("--- Rozpoczynanie...") ... do html_debtor_summary = ...)

    try:
        print("\n--- Rozpoczynanie porównywania (łączenie po kwocie) ---")
        comparison_df = pd.DataFrame()
        if df_invoices.empty and df_payments.empty:
             flash("Brak danych do porównania.", "warning")
             return redirect(url_for('.index')) # ZMIANA: .index
        elif df_invoices.empty:
             comparison_df = df_payments.copy()
             comparison_df['Status'] = 'Wpłata bez faktury (?)'
             print("Brak faktur z PDF, pokazuję tylko płatności.")
             for col in ['NrFakturyPDF', 'KontrahentPDF', 'KwotaPDF', 'NrFakturyPDF_Upper', 'Invoice_ID', 'Weryfikacja Nr Faktury', 'Różnica Kwot']:
                 if col not in comparison_df.columns: comparison_df[col] = np.nan if col == 'Różnica Kwot' else ('-' if 'Nr' in col or 'Kontra' in col else 0)
        elif df_payments.empty:
             comparison_df = df_invoices.copy()
             comparison_df['Status'] = 'NIEOPŁACONA'
             print("Brak płatności z CSV, pokazuję tylko faktury (poza PA).")
             for col in list(CSV_DISPLAY_NAMES.values()) + ['NrFaktury_z_Tytulu', 'Payment_ID', 'NrFaktury_z_Tytulu_Upper', 'Weryfikacja Nr Faktury', 'Różnica Kwot']:
                 if col not in comparison_df.columns: comparison_df[col] = np.nan if col == 'Różnica Kwot' else ('-' if 'Nr' in col or 'Tytuł' in col or 'Od Kogo' in col else 0)
        else:
            comparison_df = pd.merge(
                df_invoices, df_payments, on='Kwota_MergeKey', how='outer', suffixes=('_Faktura', '_Wplata')
            )
            comparison_df = comparison_df.drop(columns=['Kwota_MergeKey'])
            print(f"Połączono dane. Rozmiar tabeli porównawczej: {comparison_df.shape}")

        # --- Analiza statusu płatności ---
        kwota_wplaty_col = 'Kwota Wpłaty'
        kwota_pdf_col = 'KwotaPDF'
        kontrahent_pdf_col = 'KontrahentPDF'
        nr_faktury_pdf_col = 'NrFakturyPDF'
        nr_faktury_pdf_upper_col = 'NrFakturyPDF_Upper'
        nr_faktury_tytul_col = 'NrFaktury_z_Tytulu'
        nr_faktury_tytul_upper_col = 'NrFaktury_z_Tytulu_Upper'

        for col in [kwota_wplaty_col, kwota_pdf_col]:
            if col not in comparison_df.columns: comparison_df[col] = np.nan
            comparison_df[col] = pd.to_numeric(comparison_df[col], errors='coerce').fillna(0)
        for col in [kontrahent_pdf_col, nr_faktury_pdf_col, nr_faktury_tytul_col]:
             if col not in comparison_df.columns: comparison_df[col] = '-'
             comparison_df[col] = comparison_df[col].fillna('-').astype(str)
        for col in [nr_faktury_pdf_upper_col, nr_faktury_tytul_upper_col]:
             if col not in comparison_df.columns: comparison_df[col] = ''
             comparison_df[col] = comparison_df[col].fillna('').astype(str)

        conditions = [
            (comparison_df[kwota_pdf_col] > 0) & (comparison_df[kwota_wplaty_col] > 0),
            (comparison_df[kwota_pdf_col] > 0) & (comparison_df[kwota_wplaty_col] == 0),
            (comparison_df[kwota_pdf_col] == 0) & (comparison_df[kwota_wplaty_col] > 0)
        ]
        choices = ['Do weryfikacji', 'NIEOPŁACONA', 'Wpłata bez faktury (?)']
        comparison_df['Status'] = np.select(conditions, choices, default='Błąd statusu')

        comparison_df['Różnica Kwot'] = np.where(
            conditions[0], comparison_df[kwota_wplaty_col] - comparison_df[kwota_pdf_col], np.nan
        )

        comparison_df['Status'] = np.where(
            (comparison_df['Status'] == 'Do weryfikacji') & (abs(comparison_df['Różnica Kwot']) < AMOUNT_TOLERANCE),
            'OPŁACONA', comparison_df['Status']
        )
        comparison_df['Status'] = np.where(
            (comparison_df['Status'] == 'Do weryfikacji') & (abs(comparison_df['Różnica Kwot']) >= AMOUNT_TOLERANCE),
            'BŁĘDNA KWOTA', comparison_df['Status']
        )

        comparison_df['Weryfikacja Nr Faktury'] = np.where(
             (comparison_df['Status'].isin(['OPŁACONA', 'BŁĘDNA KWOTA'])) & \
             (comparison_df[nr_faktury_pdf_upper_col] == comparison_df[nr_faktury_tytul_upper_col]) & \
             (comparison_df[nr_faktury_pdf_upper_col] != ''), 'OK',
             np.where((comparison_df['Status'].isin(['OPŁACONA', 'BŁĘDNA KWOTA'])), 'Sprawdź Nr', '-')
        )

        # --- Podział na sekcje ---
        df_paid = comparison_df[comparison_df['Status'].isin(['OPŁACONA', 'BŁĘDNA KWOTA'])].copy()
        df_unpaid = comparison_df[comparison_df['Status'] == 'NIEOPŁACONA'].copy()
        df_other_payments = comparison_df[comparison_df['Status'] == 'Wpłata bez faktury (?)'].copy()

        # --- Obliczanie sum ---
        sum_paid_val = 0.0
        sum_unpaid_val = 0.0
        if not df_paid.empty and kwota_pdf_col in df_paid.columns:
            sum_paid_val = pd.to_numeric(df_paid[kwota_pdf_col], errors='coerce').sum()
        if not df_unpaid.empty and kwota_pdf_col in df_unpaid.columns:
            sum_unpaid_val = pd.to_numeric(df_unpaid[kwota_pdf_col], errors='coerce').sum()
        sum_paid_str = f"{sum_paid_val:.2f}".replace('.', ',')
        sum_unpaid_str = f"{sum_unpaid_val:.2f}".replace('.', ',')
        print(f"Suma opłaconych faktur (PDF): {sum_paid_str}")
        print(f"Suma nieopłaconych faktur (PDF): {sum_unpaid_str}")

        # --- Oznaczanie powtarzających się kontrahentów w NIEOPŁACONYCH ---
        if not df_unpaid.empty and kontrahent_pdf_col in df_unpaid.columns:
            df_unpaid[kontrahent_pdf_col] = df_unpaid[kontrahent_pdf_col].fillna('-').astype(str)
            kontrahent_counts = df_unpaid[kontrahent_pdf_col].value_counts()
            repeating_kontrahents = kontrahent_counts[kontrahent_counts > 1].index.tolist()
            df_unpaid['Repeat_Kontrahent'] = df_unpaid[kontrahent_pdf_col].isin(repeating_kontrahents)
            print(f"Oznaczono {len(repeating_kontrahents)} powtarzających się kontrahentów w sekcji nieopłaconych.")
        elif kontrahent_pdf_col in df_unpaid.columns:
             df_unpaid['Repeat_Kontrahent'] = False

        # === SEKCJA SORTOWANIA - PRZYWRÓCONA POPRZEDNIA LOGIKA ===
        def extract_invoice_parts(series):
            # Wyciąga rok, miesiąc, numer z numeru faktury
            extracted = series.astype(str).str.extract(r'(\d+)/(\d{2})/(\d{4})', expand=True)
            if extracted.shape[1] == 3:
                year = pd.to_numeric(extracted.iloc[:, 2], errors='coerce').fillna(0).astype(int)
                month = pd.to_numeric(extracted.iloc[:, 1], errors='coerce').fillna(0).astype(int)
                num = pd.to_numeric(extracted.iloc[:, 0], errors='coerce').fillna(0).astype(int)
                return year, month, num
            else:
                default_series = pd.Series([0] * len(series), index=series.index) # Zachowaj indeks
                return default_series, default_series, default_series

        # Sortuj opłacone wg daty/numeru malejąco
        if not df_paid.empty and nr_faktury_pdf_col in df_paid.columns:
             df_paid['Sort_Year'], df_paid['Sort_Month'], df_paid['Sort_Num'] = extract_invoice_parts(df_paid[nr_faktury_pdf_col])
             df_paid = df_paid.sort_values(
                 by=['Sort_Year', 'Sort_Month', 'Sort_Num'],
                 ascending=[False, False, False],
                 na_position='last'
             ).drop(columns=['Sort_Year', 'Sort_Month', 'Sort_Num'])
             print("Posortowano sekcję opłaconych wg daty/numeru faktury.")

        # Sortuj nieopłacone wg daty/numeru malejąco
        if not df_unpaid.empty and nr_faktury_pdf_col in df_unpaid.columns:
            df_unpaid['Sort_Year'], df_unpaid['Sort_Month'], df_unpaid['Sort_Num'] = extract_invoice_parts(df_unpaid[nr_faktury_pdf_col])
            df_unpaid = df_unpaid.sort_values(
                by=['Sort_Year', 'Sort_Month', 'Sort_Num'],
                ascending=[False, False, False], # Przywrócone sortowanie
                na_position='last'
            ).drop(columns=['Sort_Year', 'Sort_Month', 'Sort_Num'])
            print("Posortowano sekcję nieopłaconych wg daty/numeru faktury.")

        # Sortowanie innych płatności po dacie księgowania
        if not df_other_payments.empty and 'Data Księgowania' in df_other_payments.columns:
             if 'Data Księgowania' in df_other_payments.columns:
                 df_other_payments['DataKsięgowaniaDT'] = pd.to_datetime(df_other_payments['Data Księgowania'], dayfirst=True, errors='coerce')
                 df_other_payments = df_other_payments.sort_values(by='DataKsięgowaniaDT', ascending=False, na_position='last').drop(columns=['DataKsięgowaniaDT'])
                 print("Posortowano sekcję innych wpłat.")
        # === KONIEC SEKCJI SORTOWANIA ===

        # --- NOWA SEKCJA: Podsumowanie dłużników ---
        df_debtor_summary = pd.DataFrame()
        if not df_unpaid.empty:
            print("Generowanie podsumowania dłużników...")
            try:
                df_debtor_summary = df_unpaid.groupby('KontrahentPDF').agg(
                    CalkowiteZadluzenie=('KwotaPDF', 'sum'),
                    LiczbaFaktur=('NrFakturyPDF', 'count')
                ).reset_index()
                df_debtor_summary = df_debtor_summary.sort_values(by='CalkowiteZadluzenie', ascending=False)
                df_debtor_summary = df_debtor_summary.rename(columns={
                    'KontrahentPDF': 'Kontrahent',
                    'CalkowiteZadluzenie': 'Całkowite Zadłużenie (PLN)',
                    'LiczbaFaktur': 'Liczba Nieopłaconych Faktur'
                })
                print(f"Wygenerowano podsumowanie dla {len(df_debtor_summary)} dłużników.")
            except Exception as e:
                print(f"Błąd podczas generowania podsumowania dłużników: {e}")
        # --- KONIEC SEKCJI PODSUMOWANIA DŁUŻNIKÓW ---


        # --- Wybór kolumn i formatowanie dla każdej sekcji ---
        
        # === ZMIENIONA LINIA ===
        paid_cols = ['NrFakturyPDF', 'KontrahentPDF', 'KwotaPDF', 'Status', 'Kwota Wpłaty', 'Różnica Kwot', 'NrFaktury_z_Tytulu', 'Data Księgowania']
        # =======================
        
        unpaid_cols = ['NrFakturyPDF', 'KwotaPDF', 'KontrahentPDF', 'Status', 'Repeat_Kontrahent'] # Flaga potrzebna do HTML
        other_cols = ['Kwota Wpłaty', 'NrFaktury_z_Tytulu', 'Data Księgowania', 'Tytuł Przelewu (Wpłata)', 'Od Kogo (Wpłata)']
        debtor_summary_cols = ['Kontrahent', 'Całkowite Zadłużenie (PLN)', 'Liczba Nieopłaconych Faktur']

        final_names_map = {
            'NrFakturyPDF': 'Numer Faktury (PDF)', 'KontrahentPDF': 'Kontrahent (PDF)',
            'KwotaPDF': 'Kwota (PDF)', 'Kwota Wpłaty': 'Kwota (Wpłata)',
            'NrFaktury_z_Tytulu': 'Nr Faktury (Tytuł Wpłaty)'
        }

        def format_and_generate_html(df, columns_to_show, rename_map, add_repeat_class=False):
            if df.empty: return ""
            # Upewnij się, że kolumny do formatowania istnieją
            existing_cols = [col for col in columns_to_show if col in df.columns]
            if not existing_cols: return ""
            
            df_display = df[existing_cols].copy()

            row_attrs = []
            if add_repeat_class and 'Repeat_Kontrahent' in df_display.columns:
                    row_attrs = [' class="kontrahent-repeat"' if repeat else '' for repeat in df_display['Repeat_Kontrahent']]
                    df_display = df_display.drop(columns=['Repeat_Kontrahent'])

            # Formatowanie kwot
            money_cols = ['KwotaPDF', 'Kwota Wpłaty', 'Różnica Kwot', 'Całkowite Zadłużenie (PLN)']
            for col in money_cols:
                if col in df_display.columns:
                    numeric_col = pd.to_numeric(df_display[col], errors='coerce')
                    df_display[col] = numeric_col.apply(lambda x: f"{x:,.2f} PLN".replace(',', ' ').replace('.', ',') if pd.notna(x) else '-')

            # Formatowanie reszty jako string
            for col in df_display.columns:
                if col not in money_cols:
                    df_display[col] = df_display[col].astype(str).fillna('-')

            df_display = df_display.rename(columns=rename_map)
            if 'index' in df_display.columns: df_display = df_display.drop(columns=['index'])

            html = df_display.to_html(classes='table table-striped table-hover table-bordered table-sm',
                                        index=False, border=0, na_rep='-', escape=False)
            
            # Wstrzykiwanie atrybutów <tr> (dla podświetlania wierszy)
            if add_repeat_class and row_attrs:
                html_lines = html.splitlines()
                tr_index = 0
                output_html_lines = []
                tbody_found = False
                for line in html_lines:
                    if '<tbody>' in line: tbody_found = True
                    if '</tbody>' in line: tbody_found = False
                    if tbody_found and line.strip().startswith('<tr>'):
                        if tr_index < len(row_attrs):
                            line = line.replace('<tr>', f'<tr{row_attrs[tr_index]}>', 1)
                            tr_index += 1
                    output_html_lines.append(line)
                html = "\n".join(output_html_lines)
            
            return html

        html_paid = format_and_generate_html(df_paid, paid_cols, final_names_map)
        html_unpaid = format_and_generate_html(df_unpaid, unpaid_cols, final_names_map, add_repeat_class=True)
        html_other = format_and_generate_html(df_other_payments, other_cols, final_names_map)
        html_debtor_summary = format_and_generate_html(df_debtor_summary, debtor_summary_cols, {})

        # --- ZAPIS DO DZIENNIKA AKTYWNOŚCI ---
        log_activity(
            f"Wygenerował raport dłużników (CSV: {csv_file.filename}, PDF: {', '.join(processed_pdf_filenames) if processed_pdf_filenames else 'Brak'})",
            'debtor_tracker.index' # Link do strony głównej modułu
        )

        # Przekazanie do szablonu
        return render_template('results.html',
                                table_paid_html=html_paid,
                                table_unpaid_html=html_unpaid,
                                table_other_html=html_other,
                                html_debtor_summary=html_debtor_summary, # NOWA ZMIENNA
                                sum_paid_str=sum_paid_str,
                                sum_unpaid_str=sum_unpaid_str,
                                csv_filename=csv_file.filename,
                                pdf_filenames=", ".join(processed_pdf_filenames) if processed_pdf_filenames else "Brak przetworzonych plików PDF")

    except Exception as e:
        flash(f"Błąd podczas porównywania lub formatowania danych: {e}", 'error')
        print(f"Błąd porównania/formatowania: {e}")
        import traceback; traceback.print_exc()
        return redirect(url_for('.index')) # ZMIANA: .index

# --- USUNIĘTO SEKCJE 'app.secret_key' oraz 'if __name__ == "__main__":' ---