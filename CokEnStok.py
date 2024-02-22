from ttkthemes import ThemedTk, ThemedStyle
import tkinter as tk, threading, os, shutil, datetime, sqlite3, json, csv, openpyxl, zipfile, matplotlib, matplotlib.pyplot as plt, smtplib, ctypes, urllib.parse, yaml, webbrowser
from tkinter import ttk, simpledialog, messagebox, filedialog, scrolledtext
from email.mime.text import MIMEText
from PIL import Image, ImageTk
from cryptography.fernet import Fernet

try:
    # Try to set DPI awareness to make text and elements clear
    ctypes.windll.shcore.SetProcessDpiAwareness(1) # 1: System DPI aware, 2: Per monitor DPI aware
except AttributeError:
    # Fallback if SetProcessDpiAwareness does not exist (Windows versions < 8.1)
    ctypes.windll.user32.SetProcessDPIAware()

# Global variables
search_text = ""
search_timer = None
current_record_id = None
deleted_tables = {}  # Dictionary to store deleted tables
current_db = 'it_inventory.db'  # Default database
alert_settings = {}
email_addresses = []
current_db_index = 0  # Global variable to keep track of the current database index

def get_json_filename(db_name):
    return db_name.replace('.db', '.json')

def load_category_fields_from_json(db_name):
    json_filename = get_json_filename(db_name)

    try:
        with open(json_filename, 'r') as file:
            category_fields = json.load(file)
            return category_fields
    except FileNotFoundError:
        return default_category_fields.copy()  # Return default if file not found

def save_category_fields_to_json(db_name, category_fields, tab_order=None):
    json_filename = get_json_filename(db_name)
    data_to_save = {format_table_name_for_json(table_name): fields for table_name, fields in category_fields.items()}
    if tab_order:
        formatted_tab_order = [format_table_name_for_json(table_name) for table_name in tab_order]
        data_to_save = {"tab_order": formatted_tab_order, "category_fields": data_to_save}
    with open(json_filename, 'w') as file:
        json.dump(data_to_save, file)

def save_online_database():
    # Open directory dialog to select a directory to save the files
    save_dir = filedialog.askdirectory(
        title="Select Directory to Save Online Database"
    )
    if save_dir:
        try:
            # Generate a timestamp for the archive name
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            archive_name = os.path.join(save_dir, os.path.basename(current_db).replace('.db', '') + f"_{timestamp}.zip")

            # Create a zip archive
            with zipfile.ZipFile(archive_name, 'w') as archive:

                # Add database file to the archive
                archive.write(current_db, os.path.basename(current_db))

                # Add JSON file to the archive
                json_file = get_json_filename(current_db)
                if os.path.exists(json_file):
                    archive.write(json_file, os.path.basename(json_file))

                # Add action log file to the archive
                log_file = "database_actions_log.json"
                if os.path.exists(log_file):
                    archive.write(log_file, os.path.basename(log_file))

            messagebox.showinfo("Save Complete", f"Database files saved as '{archive_name}' successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving database files: {e}")
def browse_online_database():
    # Display a warning message
    messagebox.showwarning(
        "Select ZIP File",
        "Please select the ZIP file containing the database file (db_name.db), its JSON configuration file (db_name.json), "
        "and the database actions log file (database_actions_log.json)."
    )

    # Open file dialog to select the ZIP file
    zip_file_path = filedialog.askopenfilename(
        title="Select ZIP File",
        filetypes=[("ZIP Files", "*.zip")]
    )
    if not zip_file_path:
        return

    try:
        new_db_path = ""
        # Extract the ZIP file
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            for file_name in zip_ref.namelist():
                zip_ref.extract(file_name, '.')
                if file_name.endswith('.db'):
                    new_db_path = file_name

        if new_db_path:
            load_database(new_db_path)

        messagebox.showinfo("Import Complete", "Database files imported and loaded successfully.")
    except Exception as e:
        messagebox.showerror("Error", f"Error importing and loading database files: {e}")

# Define a global variable for default category fields
default_category_fields = {
    "Computer": ["Brand", "Model", "Owner", "Serial", "Status"],
    "Smartphone": ["Brand", "Model", "Serial", "Status"],
    "Tablet": ["Brand", "Model", "Serial", "Status"],
    "Headset": ["Brand", "Model", "Status"],
    "Keyboard": ["Brand", "Layout", "Status"],
    "Mouse": ["Brand", "Status"],
    "Bag": ["Brand", "Type", "Status"],
    "Dock Station": ["Brand", "Watt", "Status"],
    "Screen": ["Brand", "Size", "Status"],
    "SIM": ["Carrier", "Status"],
    "Privacy Screen": ["Brand", "Size", "Status"],
    "Smartphone Case": ["Brand", "Compatible", "Status"],
    "Smartphone Charger": ["Brand", "Connection", "Status"],
    "Laptop Charger": ["Brand", "Connection", "Watt","Status"]
}

def create_config_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()

def load_category_fields_from_db():
    with sqlite3.connect(current_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = 'category_fields'")
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        else:
            return {}

def save_category_fields_to_db(conn, category_fields):
    cursor = conn.cursor()
    value = json.dumps(category_fields)
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('category_fields', ?)", (value,))


# Call this function at the start of your application
# category_fields = load_category_fields()

# Function to create the tables in a new database
def create_tables_in_new_db(conn, category_fields):
    cursor = conn.cursor()

    # Create the item_transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            transaction_type TEXT,
            transaction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Rest of the existing code to create other tables
    for category, fields in category_fields.items():
        table_name = category.replace(" ", "_").lower()
        columns_sql = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        columns_sql += [f"{field.lower().replace(' ', '_')} TEXT" for field in fields]
        columns_sql_str = ", ".join(columns_sql)
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql_str})"
        cursor.execute(create_table_sql)

    conn.commit()

# Function to create a new database
def create_database(custom_table=None, custom_columns=None):
    db_name = simpledialog.askstring("Create Database", "Enter Database Name:", parent=root)
    if db_name:
        if not db_name.endswith('.db'):
            db_name += '.db'
        try:
            # Create and set up the new database
            conn = sqlite3.connect(db_name)
            create_config_table(conn)
            if custom_table and custom_columns:
                cursor = conn.cursor()
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {custom_table} ({custom_columns})")
                cursor.close()
            else:
                create_tables_in_new_db(conn, default_category_fields)
            conn.close()

            # Create and save the corresponding JSON file with default category fields
            save_category_fields_to_json(db_name, default_category_fields)

            # messagebox.showinfo("Database Created", f"Database '{db_name}' created successfully.")
            create_database_submenu()  # Refresh the database list

            # Load the newly created database
            load_database(db_name)

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Error creating database: {e}")

def load_database(db_name):
    global current_db, category_fields
    current_db = db_name
    category_fields = load_category_fields_from_json(db_name)
    update_ui()  # Refresh the UI with the loaded category fields
    current_db_label.config(text=f"Current DB: {db_name}")
    #messagebox.showinfo("Database Loaded", f"Database '{db_name}' loaded successfully.")

def select_database():
    global current_db
    db_files = list_databases()  # Get a list of database files

    if db_files:
        selected_db = simpledialog.askstring("Select Database", "Enter Database Name:", parent=root)
        if selected_db:
            if not selected_db.endswith('.db'):
                selected_db += '.db'

            if selected_db in db_files:
                current_db = selected_db
                current_db_label.config(text=f"Current DB: {selected_db}")  # Update the label
                messagebox.showinfo("Database Selected", f"Database '{selected_db}' selected successfully.")
                # Refresh UI to reflect the newly loaded database
                for category in category_fields:
                    populate_list(category)
            else:
                messagebox.showerror("Error", "Database not found.")
    else:
        messagebox.showinfo("No Databases", "No databases available to select.")

# Database functions
def create_connection():
    global current_db
    conn = sqlite3.connect(current_db)
    return conn

def create_tables():
    conn = create_connection()
    cursor = conn.cursor()

    for category, fields in category_fields.items():
        table_name = category.replace(" ", "_").lower()

        # Construct the SQL statement with dynamic fields
        columns_sql = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        columns_sql += [f"{field.lower().replace(' ', '_')} TEXT" for field in fields]
        columns_sql_str = ", ".join(columns_sql)

        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql_str})"

        # Execute the SQL statement to create the table
        cursor.execute(create_table_sql)

    conn.commit()
    conn.close()

def log_clear_transaction(conn, table_name):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO item_transactions (table_name, transaction_type) VALUES (?, 'clear')", (table_name,))
    conn.commit()

def log_transaction(conn, table_name, transaction_type):
    cursor = conn.cursor()
    table_name = table_name.lower()
    cursor.execute("INSERT INTO item_transactions (table_name, transaction_type) VALUES (?, ?)", (table_name, transaction_type))
    conn.commit()

def insert_item(category, values):
    table_name = category.replace(" ", "_").lower()

    # Fields for the specific category
    fields = category_fields[category]
    columns = [field.lower().replace(' ', '_') for field in fields]

    # Construct the SQL query dynamically
    columns_str = ', '.join(columns)
    placeholders = ', '.join('?' * len(columns))
    sql_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(sql_query, values[:len(columns)])
    conn.commit()

    # Log the insertion
    log_transaction(conn, table_name, 'add')

    # Log action to JSON (for Snitch functionality)
    item_details = {"table": table_name, "values": values}
    log_action_to_json(current_db, "add", item_details)

    conn.close()

def add_item(category, entries):
    entry_values = [entry.get().strip().upper() if entry.get() else None for entry in entries]

    # Normalize status to be uppercase and without surrounding whitespace
    # Assuming 'status' is always one of the fields
    entry_values = [value.strip().upper() if value else value for value in entry_values]

    insert_item(category, tuple(entry_values))
    for entry in entries:
        entry.delete(0, tk.END)
    populate_list(category)
    update_overview()
    update_combobox_entries(category, entries)  # Update Combobox values

def add_new_column(table_name):
    # Prompt for new column name and type
    new_column_name = simpledialog.askstring("Add New Column", "Enter the name for the new column:")
    if not new_column_name:
        return

    new_column_type = simpledialog.askstring("Add New Column", "Enter the type for the new column (e.g., TEXT, INTEGER):")
    if not new_column_type:
        return

    # Add the new column to the database
    try:
        with sqlite3.connect(current_db) as conn:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {new_column_name} {new_column_type};")
            conn.commit()

        # Update category_fields and the UI
        category_fields[table_name].append(new_column_name)
        save_category_fields_to_json(current_db, category_fields)
        update_ui()

        messagebox.showinfo("Success", f"New column '{new_column_name}' added to table '{table_name}'.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error adding new column: {e}")

def fetch_items(category, field_name=None, value=None):
    table_name = category.replace(" ", "_").lower()
    conn = create_connection()
    cursor = conn.cursor()

    # If a specific field and value are provided, fetch based on that
    if field_name and value is not None:
        query = f"SELECT * FROM {table_name} WHERE {field_name} = ?"
        cursor.execute(query, (value,))
    else:
        # Otherwise, fetch all items from the category
        select_fields = ['id'] + [field.lower().replace(' ', '_') for field in category_fields[category]]
        select_statement = ', '.join(select_fields)
        query = f"SELECT {select_statement} FROM {table_name}"
        cursor.execute(query)

    rows = cursor.fetchall()
    conn.close()
    return rows


def populate_treeview(category, records):
    tree = tabs[category]['tree']
    tree.delete(*tree.get_children())  # Clear existing records
    for record in records:
        tree.insert('', 'end', values=record)

def on_tree_select(event, category):
    global current_record_id  # Declare that we'll use the global variable
    tree = tabs[category]['tree']
    entries = tabs[category]['entries']

    selected = tree.selection()
    if selected:
        # The first value in the item's values list is assumed to be the ID
        current_record_id = tree.item(selected[0], 'values')[0]

        # The rest of the values are for the ComboBoxes
        # Assuming the order of values corresponds to the order of entries
        for entry, value in zip(entries, tree.item(selected[0], 'values')[1:]):
            if isinstance(entry, ttk.Combobox):
                entry.set(value)
            elif isinstance(entry, tk.Entry):  # If you have any tk.Entry widgets
                entry.delete(0, tk.END)
                entry.insert(0, value)

def treeview_sort_column(tree, col, reverse):
    """ Function to sort treeview content when a column header is clicked. """
    l = [(tree.set(k, col), k) for k in tree.get_children('')]
    l.sort(reverse=reverse)

    # Rearrange items in sorted positions
    for index, (val, k) in enumerate(l):
        tree.move(k, '', index)

    # Reverse sort next time
    tree.heading(col, command=lambda: treeview_sort_column(tree, col, not reverse))

def create_overview_tab():
    frame = ttk.Frame(notebook)
    notebook.add(frame, text="Overview")

    # Checkbox for filtering
    real_var = tk.BooleanVar()
    real_checkbox = ttk.Checkbutton(frame, text="REAL", variable=real_var, command=update_overview)
    real_checkbox.pack()

    tree = ttk.Treeview(frame, columns=('Category Name', 'Total'), show='headings')
    tree.heading('Category Name', text='Category Name')
    tree.column('Category Name', stretch=tk.YES, minwidth=100, anchor='center')  # Center align column
    tree.heading('Total', text='Total')
    tree.column('Total', stretch=tk.YES, minwidth=100, anchor='center')  # Center align column
    tree.pack(fill='both', expand=True)

    tabs['Overview'] = {'frame': frame, 'tree': tree, 'real_var': real_var}
    update_overview()

def update_overview():
    if 'Overview' in tabs:
        real_status = tabs['Overview']['real_var'].get()
        tree = tabs['Overview']['tree']
        tree.delete(*tree.get_children())
        totals = calculate_totals(real_status)
        for category, total in totals.items():
            tree.insert('', 'end', values=(category, total))

def calculate_totals(real_status=False):
    conn = create_connection()
    cursor = conn.cursor()
    totals = {}
    for category in category_fields.keys():
        table_name = category.replace(" ", "_").lower()
        if real_status:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE UPPER(status) = 'OK'")
        else:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        totals[category] = count
    conn.close()
    return totals

# Function to change the theme
def change_theme(theme_name):
    style.set_theme(theme_name)

def populate_list(category):
    tree = tabs[category]['tree']
    tree.delete(*tree.get_children())  # Clear existing records

    records = fetch_items(category)  # Fetch items for the category
    for record in records:
        tree.insert('', 'end', values=record)

    # Update the record count label
    record_count_label = tabs[category]['record_count_label']
    record_count_label.config(text=f"Records: {len(records)}")

def on_combobox_select(event, category, field_name, combobox):
    # Get the value selected in the ComboBox
    selected_value = combobox.get().strip()

    # Fetch the items from the database that match the selected value for the given field
    records = fetch_items_by_field(category, field_name, selected_value)

    # Populate the treeview with the fetched records
    populate_treeview(category, records)

    # Update the record count label
    record_count_label = tabs[category]['record_count_label']
    record_count_label.config(text=f"Records: {len(records)}")


def fetch_items_by_field(category, field_name, value):
    table_name = category.replace(" ", "_").lower()
    conn = create_connection()
    cursor = conn.cursor()
    # Use parameterized query to prevent SQL injection
    query = f"SELECT * FROM {table_name} WHERE {field_name} = ?"
    cursor.execute(query, (value,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def clear_fields_and_update(category, entries, tree):
    for entry in entries:
        if isinstance(entry, ttk.Combobox):
            entry.set('')  # Clear Combobox
        else:
            entry.delete(0, tk.END)  # Clear Entry
    populate_list(category)  # Refresh the TreeView

def fetch_distinct_values(field, category):
    """Fetch distinct values for a field in the database."""
    try:
        table_name = category.replace(" ", "_").lower()
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT {field} FROM {table_name}")
        values = [item[0] for item in cursor.fetchall() if item[0] is not None]
        conn.close()
        return values
    except sqlite3.Error as e:
        print(f"Error fetching distinct values: {e}")
        return []

def update_combobox_entries(category, entries):
    for entry in entries:
        if isinstance(entry, ttk.Combobox):
            field = entry._name  # Assuming _name stores the field name
            values = fetch_distinct_values(field, category)
            entry['values'] = values

def highlight_matching_items(tree, search_text):
    # Define tag for highlighting
    tree.tag_configure('highlight', background='yellow')

    # Search and highlight items
    search_text = search_text.lower()
    for item in tree.get_children():
        # Clear previous tag
        tree.item(item, tags=())

        values = [str(v).lower() for v in tree.item(item, 'values')]
        if any(search_text in value for value in values):
            # Add highlight tag to this item
            tree.item(item, tags=('highlight',))

def reset_search():
    global search_text
    search_text = ""

def on_key_release(event, category):
    global search_text, search_timer

    if search_timer is not None:
        search_timer.cancel()  # Cancel the existing timer

    # Accumulate the search text
    if event.keysym == 'BackSpace':
        search_text = search_text[:-1]  # Remove last character on backspace
    elif event.keysym.lower() in ('shift_l', 'shift_r', 'alt_l', 'alt_r', 'ctrl_l', 'ctrl_r', 'caps_lock'):
        pass  # Ignore modifier keys
    else:
        search_text += event.char

    if search_text:
        highlight_matching_items(tabs[category]['tree'], search_text)
    else:
        clear_highlight(tabs[category]['tree'])

    # Start a new timer
    search_timer = threading.Timer(2.0, reset_search)  # Reset search text after 2 seconds of inactivity
    search_timer.start()
def clear_highlight(tree):
    for item in tree.get_children():
        tree.item(item, tags=())

def on_combobox_focus_in(event, combo, field):
    # Clear the combobox if it contains the default field name
    if combo.get() == field:
        combo.set('')

def on_combobox_focus_out(event, combo, field):
    # Reset the default field name if the combobox is left empty
    if not combo.get():
        combo.set(field)

def list_databases():
    """ List all .db files in the current directory """
    return [f for f in os.listdir('.') if os.path.isfile(f) and f.endswith('.db')]

def select_all(tree):
    """Select all items in the given Treeview."""
    tree.selection_set(tree.get_children())

def select_next_database():
    global current_db_index
    db_files = list_databases()
    if current_db_index < len(db_files) - 1:
        current_db_index += 1
        load_database(db_files[current_db_index])

def select_previous_database():
    global current_db_index
    db_files = list_databases()
    if current_db_index > 0:
        current_db_index -= 1
        load_database(db_files[current_db_index])

def create_db_shortcut():
    # Mimic the action of "Create Table"
    create_database(custom_table=None, custom_columns=None)

def add_table_shortcut():
    table_name = simpledialog.askstring("Add Table", "Enter the name of the table to add:")
    columns = simpledialog.askstring("Add Table", "Enter additional columns (e.g., 'name TEXT, age INT'):")

    if table_name and columns:
        formatted_table_name = format_table_name_for_json(table_name)
        create_table_sql = f"CREATE TABLE IF NOT EXISTS {formatted_table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns});"
        try:
            with sqlite3.connect(current_db) as conn:
                cursor = conn.cursor()
                cursor.execute(create_table_sql)

            # Exclude 'id' from new_columns and update category_fields
            new_columns = [col.split()[0] for col in columns.split(',') if col.split()[0].lower() != 'id']
            category_fields[formatted_table_name] = new_columns

            # Refresh the UI and save the updated category_fields to JSON
            update_ui()
            save_category_fields_to_json(current_db, category_fields)

            messagebox.showinfo("Success", f"Table '{formatted_table_name}' added successfully.")
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Error creating table: {e}")
    else:
        messagebox.showwarning("Warning", "Table name and columns are required.")

def open_warning_level_settings(event=None):
    open_warning_level_window()

def open_graphic_menu(event=None):
    # Assuming you have a function to open the Graphic menu
    open_evolution_window()

def open_shortcut_snitch(event=None):
    # Assuming you have a function to open the Snitch window
    open_snitch_window()

def open_about_window(event=None):
    about()

def open_shortcut_keyboard(event=None):
    open_keyboard_shortcuts_window()

def wipe_out_db(event=None):
    # Assuming you have a function to wipe out the database
    wipe_current_database()

def backup_db(event=None):
    # Assuming you have a function to backup the database
    backup_database()

def start_as_new_db(event=None):
    # Assuming you have a function to start as a new database
    start_as_new_database()

def configure_email_account(event=None):
    # Assuming you have a function to configure the email account
    open_email_config_window()

def create_database_submenu():
    select_db_menu.delete(0, tk.END)  # Clear existing menu items
    db_files = list_databases()  # Get an updated list of database files
    for db in db_files:
        select_db_menu.add_command(label=db, command=lambda db=db: load_database(db))

def backup_database():
    global current_db
    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_db_name = f"{current_db.split('.')[0]}_{timestamp}.db"

    try:
        shutil.copyfile(current_db, backup_db_name)
        messagebox.showinfo("Backup Successful", f"Database backed up as {backup_db_name}")
    except Exception as e:
        messagebox.showerror("Backup Failed", str(e))

    # Refresh the GUI after backup
    refresh_gui()

def clear_current_table():
    global current_db
    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    selected_tab = notebook.select()
    tab_text = notebook.tab(selected_tab, "text")
    if tab_text == "Overview":
        messagebox.showinfo("Error", "Cannot clear the Overview tab.")
        return

    confirm = messagebox.askyesno("Clear Current Table", f"Are you sure you want to clear all records in the table '{tab_text}'?")
    if confirm:
        try:
            table_name = tab_text.replace(" ", "_").lower()
            conn = sqlite3.connect(current_db)
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")

            # Log a 'clear' transaction for the table
            log_clear_transaction(conn, table_name)

            conn.commit()
            conn.close()

            populate_list(tab_text)
            update_overview()

            messagebox.showinfo("Table Cleared", f"All records in the table '{tab_text}' have been cleared.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

def clear_database():
    global current_db
    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    confirm = messagebox.askyesno("Clear Database", "Are you sure you want to erase all records in the database?")
    if confirm:
        try:
            conn = sqlite3.connect(current_db)
            cursor = conn.cursor()

            for category in category_fields.keys():
                table_name = category.replace(" ", "_").lower()
                cursor.execute(f"DELETE FROM {table_name}")

                # Log a 'clear' transaction
                log_clear_transaction(conn, table_name)

            conn.commit()
            conn.close()

            for category in category_fields.keys():
                populate_list(category)

            messagebox.showinfo("Database Cleared", "All records have been erased.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

def wipe_current_database():
    global current_db
    if not current_db or current_db == 'it_inventory.db':  # Default DB or no DB selected
        messagebox.showinfo("Error", "No database loaded or default database cannot be deleted.")
        return

    # Confirm with the user
    confirm = messagebox.askyesno("Wipe Database", f"Are you sure you want to delete the database '{current_db}' and its associated JSON file?")
    if confirm:
        try:
            # Delete the database file
            os.remove(current_db)
            # messagebox.showinfo("Database Deleted", f"Database '{current_db}' has been deleted.")

            # Delete the associated JSON file
            json_file = current_db.replace('.db', '.json')
            if os.path.exists(json_file):
                os.remove(json_file)
                # messagebox.showinfo("JSON File Deleted", f"JSON file '{json_file}' has been deleted.")

            # Reset the current database to the default or None
            reset_to_default_db()
            create_database_submenu()  # Refresh the database selection menu
            refresh_gui()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete database and JSON file: {e}")

def reset_to_default_db():
    global current_db
    current_db = 'it_inventory.db'  # Reset to your default database
    current_db_label.config(text=f"Current DB: {current_db}")

def on_focus_in(event):
    widget = event.widget
    widget.delete(0, tk.END)

def on_focus_out(event):
    widget = event.widget
    default_value = widget._name  # Assuming _name stores the default value

    # Capitalize the first letter and make the rest lowercase
    formatted_default_value = default_value[0].upper() + default_value[1:].lower()

    if not widget.get():
        if isinstance(widget, ttk.Combobox):
            widget.set(formatted_default_value)
        elif isinstance(widget, tk.Entry):
            widget.insert(0, formatted_default_value)

def format_table_name_for_display(table_name):
    """Convert table name from internal format (with underscores) to display format (with spaces)."""
    return table_name.replace("_", " ")

def format_table_name_for_db(table_name):
    """Convert table name from display format (with spaces) to internal format (with underscores)."""
    return table_name.replace(" ", "_")

def format_table_name_for_json(table_name):
    return table_name.strip().lower().replace(" ", "_")

def Edit_Database():
    action = simpledialog.askstring("Edit Database", "Type 'add' to add a table or 'remove' to remove a table.")

    if action == 'add':
        table_name = simpledialog.askstring("Add Table", "Enter the name of the table to add:")
        columns = simpledialog.askstring("Add Table", "Enter additional columns (e.g., 'name TEXT, age INT'):")

        if table_name and columns:
            formatted_table_name = format_table_name_for_json(table_name)
            create_table_sql = f"CREATE TABLE IF NOT EXISTS {formatted_table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns});"
            try:
                with sqlite3.connect(current_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute(create_table_sql)

                # Exclude 'id' from new_columns and update category_fields
                new_columns = [col.split()[0] for col in columns.split(',') if col.split()[0].lower() != 'id']
                category_fields[formatted_table_name] = new_columns

                # Refresh the UI and save the updated category_fields to JSON
                update_ui()
                save_category_fields_to_json(current_db, category_fields)

                messagebox.showinfo("Success", f"Table '{formatted_table_name}' added successfully.")
            except sqlite3.Error as e:
                messagebox.showerror("Error", f"Error creating table: {e}")
        else:
            messagebox.showwarning("Warning", "Table name and columns are required.")

    elif action == 'remove':
        table_names = simpledialog.askstring("Remove Table",
                                             "Enter the names of the table(s) to remove (separated by commas):")

        if table_names:
            for table_name in table_names.split(','):
                table_name = table_name.strip()  # Remove leading/trailing spaces
                # Enclose the table name in double quotes for safety
                safe_table_name = f'"{table_name}"'
                confirm = messagebox.askyesno("Delete Table",
                                              f"Are you sure you want to delete the table '{table_name}'?")

                if not confirm:
                    continue

                try:
                    with sqlite3.connect(current_db) as conn:
                        cursor = conn.cursor()
                        cursor.execute(f"DROP TABLE IF EXISTS {safe_table_name};")
                        conn.commit()

                    # Remove the table from category_fields and update the UI
                    if table_name in category_fields:
                        del category_fields[table_name]
                        save_category_fields_to_json(current_db, category_fields)

                except sqlite3.Error as e:
                    messagebox.showerror("Error", f"Error removing table '{table_name}': {e}")

            # Refresh the UI after all deletions are processed
            update_ui()
            # messagebox.showinfo("Success", "Tables removed successfully.")
        else:
            messagebox.showwarning("Warning", "Table name(s) are required.")
    else:
        messagebox.showinfo("Edit Database", "Invalid action. Please type 'add' or 'remove'.")

def update_ui():
    # Reload the entire GUI components
    # Clear existing tabs and recreate them
    for tab in notebook.tabs():
        notebook.forget(tab)

    # Recreate the tabs for different categories
    global tabs
    tabs = {category: {'frame': None, 'entries': None, 'tree': None, 'record_count_label': None} for category in category_fields}
    for category, fields in category_fields.items():
        create_tab(category, fields)

    # Recreate the Overview tab
    create_overview_tab()

    # Refresh the database submenu to reflect any changes
    create_database_submenu()

def browse_and_copy_databases():
    # Open file dialog to select database files
    db_files = filedialog.askopenfilenames(
        title="Select Database Files",
        filetypes=[("SQLite Database Files", "*.db")]
    )
    if not db_files:
        return

    for db_file in db_files:
        # Copy each file to the application's root directory
        db_filename = os.path.basename(db_file)
        shutil.copy(db_file, db_filename)

        # Create corresponding JSON file with default category fields
        save_category_fields_to_json(db_filename, default_category_fields)

    # Refresh the database submenu to include the new databases
    create_database_submenu()

    # Load the last browsed database
    load_database(db_filename)

    #messagebox.showinfo("Databases Imported", f"Database '{db_filename}' imported and loaded successfully.")

def export_current_table_to_csv():
    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    try:
        conn = sqlite3.connect(current_db)
        cursor = conn.cursor()

        # Identify the current table based on the selected tab in the notebook
        selected_tab = notebook.select()
        tab_text = notebook.tab(selected_tab, "text")
        current_table = tab_text.replace(" ", "_").lower()

        cursor.execute(f"SELECT * FROM {current_table}")
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        # Write table data to CSV file
        csv_filename = f"{current_table}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(columns)  # Write column headers
            csvwriter.writerows(rows)

        messagebox.showinfo("Export Complete", f"Table '{current_table}' exported to CSV file successfully.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error exporting table: {e}")
def export_db_to_excel():
    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    try:
        conn = sqlite3.connect(current_db)
        cursor = conn.cursor()

        # Get the list of tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table_name[0] for table_name in cursor.fetchall()]

        # Create a new Excel workbook
        workbook = openpyxl.Workbook()
        workbook.remove(workbook.active)  # Remove default sheet

        # Process sqlite_sequence first, if it exists
        if 'sqlite_sequence' in tables:
            tables.remove('sqlite_sequence')
            tables.insert(0, 'sqlite_sequence')  # Move to the beginning

        for table_name in tables:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]

            # Create a sheet for each table
            sheet = workbook.create_sheet(title=table_name)
            sheet.append(columns)  # Write column headers
            for row in rows:
                sheet.append(row)

        # Save the workbook to an Excel file
        excel_filename = f"{current_db.replace('.db', '')}.xlsx"
        workbook.save(excel_filename)

        messagebox.showinfo("Export Complete", f"Database exported to Excel file '{excel_filename}' successfully.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error exporting database: {e}")

def save_last_used_db():
    """Save the name of the last used database to a file."""
    try:
        with open("last_db.txt", "w") as file:
            file.write(current_db)
    except Exception as e:
        print(f"Error saving last used database: {e}")

def refresh_gui():
    global current_db, category_fields

    if not current_db:
        messagebox.showinfo("Error", "No database loaded.")
        return

    # Load category fields from the JSON file
    category_fields = load_category_fields_from_json(current_db)

    # Update UI to reflect the reloaded database
    update_ui()

    current_db_label.config(text=f"Current DB: {current_db}")  # Update the label
    for category in category_fields:
        populate_list(category)

def open_evolution_window():
    evolution_window = tk.Toplevel(root)
    evolution_window.title("Evolution")
    evolution_window.iconbitmap("icons.ico")

    # Combobox for selecting a table
    table_combo = ttk.Combobox(evolution_window)
    table_combo.pack(padx=10, pady=10)

    # Fetch table names and populate the Combobox, excluding certain tables and deleted tables
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name NOT IN ('config', 'item_transactions', 'sqlite_sequence') 
        AND name NOT LIKE 'deleted_%';
    """)
    table_names = [table_name[0] for table_name in cursor.fetchall()]
    table_combo['values'] = table_names
    table_combo.set(table_names[0] if table_names else "")  # Set the first table as default

    # Placeholder for the graph
    graph_frame = ttk.Frame(evolution_window)
    graph_frame.pack(fill='both', expand=True)

    # Bind an event to update the graph when the table selection changes
    table_combo.bind("<<ComboboxSelected>>", lambda event: update_evolution_graph(graph_frame, table_combo.get()))

    # Initially display the graph for the first table
    if table_names:
        update_evolution_graph(graph_frame, table_names[0])

def fetch_evolution_data(table_name):
    conn = create_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT transaction_type, transaction_time FROM item_transactions
        WHERE table_name = ?
        ORDER BY transaction_time
    """, (table_name,))

    transactions = cursor.fetchall()

    evolution_data = []
    timestamps = []
    item_count = 0
    for transaction_type, timestamp in transactions:
        if transaction_type == 'add':
            item_count += 1
        elif transaction_type == 'delete':
            item_count -= 1
        elif transaction_type == 'clear':
            item_count = 0  # Reset item count to zero for 'clear' transaction
        evolution_data.append(item_count)
        timestamps.append(timestamp)

    conn.close()
    return evolution_data, timestamps

def update_evolution_graph(frame, table_name):
    # Clear the current contents of the frame
    for widget in frame.winfo_children():
        widget.destroy()

    evolution_data, timestamps = fetch_evolution_data(table_name)

    # Create and display the graph
    # import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    fig, ax = plt.subplots()
    ax.plot(evolution_data, marker='o', color='lightblue')
    ax.set_title(f"Evolution of items in {table_name}")
    ax.set_xlabel("Event Sequence")
    ax.set_ylabel("Total Items")

    # Determine the range for y-axis to draw horizontal lines
    y_min, y_max = ax.get_ylim()
    y_min, y_max = int(y_min), int(y_max)

    # Draw horizontal lines at each integer point within the y-axis range
    for y in range(y_min, y_max + 1):
        ax.axhline(y=y, color='lightblue', linestyle='-')

    # Format and annotate points with timestamps in two lines
    # for i, (x, y) in enumerate(zip(range(len(evolution_data)), evolution_data)):
    #     timestamp = datetime.datetime.fromisoformat(timestamps[i])
    #     formatted_timestamp = timestamp.strftime('%y%m%d\n%H.%M')  # Split into two lines
    #     ax.annotate(formatted_timestamp, (x, y), textcoords="offset points", xytext=(0, 10), ha='center')

    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(fill='both', expand=True)
    canvas.draw()

def log_action_to_json(db_name, action, item_details):
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "database": db_name,
        "action": action,
        "details": item_details
    }

    try:
        # Read existing log data
        with open("database_actions_log.json", "r") as file:
            log_data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        log_data = []

    # Append new log entry
    log_data.append(log_entry)

    # Write updated log data to file
    with open("database_actions_log.json", "w") as file:
        json.dump(log_data, file, indent=4)

def open_snitch_window():
    snitch_window = tk.Toplevel(root)
    snitch_window.title("Snitch Log")
    snitch_window.iconbitmap("icons.ico")

    # Create a scrolled text widget to display the contents of the JSON file
    text_area = scrolledtext.ScrolledText(snitch_window, wrap=tk.WORD)
    text_area.pack(fill=tk.BOTH, expand=True)

    try:
        # Load and display the contents of the JSON file
        with open("database_actions_log.json", "r") as file:
            log_data = json.load(file)
            formatted_text = json.dumps(log_data, indent=4)
            text_area.insert(tk.INSERT, formatted_text)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        text_area.insert(tk.INSERT, f"Error opening log file: {e}")

    # Make the text area read-only
    text_area.config(state=tk.DISABLED)

def rollback_last_delete():
    global deleted_tables
    if not deleted_tables:
        messagebox.showinfo("Rollback", "No recently deleted tables to restore.")
        return

    # Get the last deleted table
    original_table_name, (deleted_table_name, fields) = deleted_tables.popitem()

    try:
        with sqlite3.connect(current_db) as conn:
            cursor = conn.cursor()
            # Rename the table back to its original name
            cursor.execute(f"ALTER TABLE \"{deleted_table_name}\" RENAME TO \"{original_table_name}\";")
            conn.commit()

        # Restore the table information
        category_fields[original_table_name] = fields
        save_category_fields_to_json(current_db, category_fields)

        # Update UI
        update_ui()

        messagebox.showinfo("Success", f"Table '{original_table_name}' restored successfully.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error restoring table '{original_table_name}': {e}")

# Function to start as a new database
def start_as_new_database():
    confirm = messagebox.askyesno("Start as New Database",
                                  "Are you sure you want to remove all tables and start as a new database?")
    if not confirm:
        return

    try:
        with sqlite3.connect(current_db) as conn:
            cursor = conn.cursor()
            # Fetch all table names except system tables and item_transactions
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', 'item_transactions');")
            tables = [row[0] for row in cursor.fetchall()]

            # Drop each table
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS \"{table}\";")

            conn.commit()

        # Reset category_fields and update UI
        global category_fields
        category_fields = {}
        save_category_fields_to_json(current_db, category_fields)
        update_ui()

        messagebox.showinfo("Success", "All tables removed, you can now start as a new database.To add new tables, go to 'Edit Database' in the 'Database' menu.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error resetting database: {e}")

def open_warning_level_window(pre_fill_data=None):
    global saved_content_combo
    warning_window = tk.Toplevel(root)
    warning_window.title("Warning Level Settings")
    warning_window.iconbitmap("icons.ico")

    # Split the window into left and right frames
    left_frame = ttk.Frame(warning_window)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    right_frame = ttk.Frame(warning_window)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    # Treeview for email addresses
    email_tree = ttk.Treeview(left_frame, columns=('Email'), show='headings', height=16)
    email_tree.heading('Email', text='Recipient Email Address')
    email_tree.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky='ew')

    # Email entry field
    email_entry = ttk.Entry(left_frame)
    email_entry.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky='ew')

    # Add Email button
    add_email_button = ttk.Button(left_frame, text="Add Email",
                                  command=lambda: add_email(email_tree, email_entry.get()))
    add_email_button.grid(row=2, column=0, padx=10, pady=5)

    # Address Book button
    address_book_button = ttk.Button(left_frame, text="Address Book", command=lambda: manage_address_book(email_tree))
    address_book_button.grid(row=2, column=1, padx=10, pady=5)

    # Combobox for table selection
    table_combo = ttk.Combobox(right_frame, values=[format_table_name_for_display(table) for table in list(category_fields.keys())])
    table_combo.set("Select Table")
    table_combo.grid(row=0, column=0, padx=10, pady=5)

    # Combobox for threshold with numbers from 1 to 10
    threshold_values = [str(i) for i in range(1, 11)]
    threshold_combo = ttk.Combobox(right_frame, values=threshold_values)
    threshold_combo.set("Limit")  # Default value
    threshold_combo.grid(row=0, column=1, padx=10, pady=5)

    # Combobox for selecting YAML configuration files
    yaml_files_combo = ttk.Combobox(right_frame, values=list_yaml_files())
    yaml_files_combo.set("Select SMTP Conf")
    yaml_files_combo.grid(row=0, column=2, padx=10, pady=5)

    # Save Alert button
    save_alert_button = ttk.Button(right_frame, text="Set Up Email Alert", command=lambda: save_alert(table_combo.get(), threshold_combo.get(), email_content.get("1.0", tk.END), email_tree, yaml_files_combo.get()))
    save_alert_button.grid(row=0, column=3, padx=10, pady=5)

    # Combobox for listing saved email contents
    saved_content_combo = ttk.Combobox(right_frame)
    saved_content_combo.set("Select Mail Content")
    saved_content_combo.grid(row=1, column=0, padx=10, pady=5)

    # Assuming 'right_frame' is the frame where the "Send Test Email" button is located
    send_email_button = ttk.Button(right_frame, text="Send Email",
                                   command=lambda: send_test_email(table_combo, email_content))
    send_email_button.grid(row=1, column=3, padx=10, pady=5)

    # Button to save modified email content
    save_modified_content_button = ttk.Button(right_frame, text="Save Content Changes",
                                              command=lambda: save_modified_email_content(saved_content_combo.get(),
                                                                                          email_content.get("1.0",
                                                                                                            tk.END)))
    save_modified_content_button.grid(row=1, column=2, padx=10, pady=5)

    # Textbox for email content
    email_content = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=18)
    email_content.grid(row=2, column=0, columnspan=4, padx=10, pady=5, sticky='ew')  # Span across 3 columns

    # Button to save current email content as a favorite
    save_content_button = ttk.Button(right_frame, text="Save Content as Favorite",
                                     command=lambda: save_favorite_email_content(email_content.get("1.0", tk.END)))
    save_content_button.grid(row=1, column=1, padx=10, pady=5)

    # Add the "Send Summary Mail" button to the right frame
    send_summary_button = ttk.Button(right_frame, text="Send Summary Mail", command=send_summary_email)
    send_summary_button.grid(row=3, column=0, padx=10, pady=5)

    # Add the "See Email Alerts" button to the right frame
    see_alerts_button = ttk.Button(right_frame, text="See Email Alerts", command=open_email_alerts_window)
    see_alerts_button.grid(row=3, column=3, padx=10, pady=5)

    # Update combobox values with saved email contents
    update_saved_content_combobox(saved_content_combo)

    # Bind Backspace key to delete selected email(s)
    email_tree.bind("<BackSpace>", lambda event: delete_selected_emails(email_tree))

    # Bind event to update the textbox when a saved content is selected
    saved_content_combo.bind("<<ComboboxSelected>>",
                             lambda event: load_favorite_email_content(saved_content_combo.get(), email_content))

    # Bind Ctrl + Backspace to delete the selected email content file
    warning_window.bind("<Control-BackSpace>", delete_selected_email_content_file)

    # Bind Ctrl + Shift + S to send the summary email
    warning_window.bind("<Control-Shift-S>", send_summary_email)

    # Load email addresses and populate the tree view
    global email_addresses
    email_addresses = load_email_addresses()
    for email in email_addresses:
        email_tree.insert('', 'end', values=(email,))

    # Check if there is pre-fill data and set the fields accordingly
    if pre_fill_data:
        table_name, threshold, smtp_config_name, email_addresses = pre_fill_data
        table_combo.set(table_name)
        threshold_combo.set(threshold)
        yaml_files_combo.set(smtp_config_name)
        for email in email_addresses.split(';'):
            email_tree.insert('', 'end', values=(email,))

def add_email(email_tree, email):
    global email_addresses
    if email and email not in email_addresses:  # Check if the email is not already in the list
        email_addresses.append(email)
        email_tree.insert('', 'end', values=(email,))
        save_email_addresses(email_addresses)  # Save the updated list
        # Clear the email entry field if needed

def delete_selected_emails(tree):
    selected_items = tree.selection()
    for item in selected_items:
        tree.delete(item)
    # Update the email_addresses list to reflect the changes
    global email_addresses
    email_addresses = [tree.item(item)['values'][0] for item in tree.get_children()]
    save_email_addresses(email_addresses)

def delete_selected_email_addbook(event=None):
    selected_items = address_book_tree.selection()
    if not selected_items:
        return  # No item selected

    for item in selected_items:
        email = address_book_tree.item(item, 'values')[0]
        if email in addresses:
            addresses.remove(email)  # Remove from the list
            address_book_tree.delete(item)  # Remove from Treeview

    # Update the JSON file
    with open("address_book.json", "w") as file:
        json.dump(addresses, file)

def save_email_addresses(email_addresses):
    try:
        with open("email_addresses.json", "w") as file:
            json.dump(email_addresses, file)
    except Exception as e:
        print(f"Error saving email addresses: {e}")

def load_email_addresses():
    try:
        with open("email_addresses.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []  # Return an empty list if the file does not exist
    except Exception as e:
        print(f"Error loading email addresses: {e}")
        return []

def initialize_email_tree(tree):
    email_addresses = load_email_addresses()
    for email in email_addresses:
        tree.insert('', 'end', values=(email,))


def create_alert_logs_directory():
    alert_logs_dir = os.path.join(os.path.dirname(__file__), "alert_logs")
    if not os.path.exists(alert_logs_dir):
        os.makedirs(alert_logs_dir)
    return alert_logs_dir

def save_alert_to_file():
    with open('alert_settings.json', 'w') as file:
        json.dump(alert_settings, file)


def save_alert(table_name, threshold, email_content, email_tree, yaml_config_name):
    global alert_settings  # Declare the usage of the global variable

    # Standardize the table name for internal use by converting to lowercase and replacing spaces with underscores
    formatted_table_name = table_name.lower().replace(" ", "_")

    # Convert threshold to an integer
    try:
        threshold = int(threshold)
    except ValueError:
        messagebox.showerror("Error", "Invalid threshold value. Please enter a number.")
        return

    # Gather email addresses from the treeview
    email_addresses = [email_tree.item(item_id, 'values')[0] for item_id in email_tree.get_children()]

    if table_name and email_addresses and email_content:
        # Store the alert settings using the standardized table name
        alert_settings[formatted_table_name] = {
            "threshold": threshold,
            "email_addresses": email_addresses,
            "email_content": email_content,
            "yaml_config_name": yaml_config_name  # Include the YAML file name
        }

        # Save the alert settings log using the original table name format for user readability
        alert_logs_dir = create_alert_logs_directory()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        log_filename = os.path.join(alert_logs_dir, f"{table_name}_limit{threshold}_{timestamp}.txt")
        with open(log_filename, 'w') as log_file:
            log_file.write(f"Table: {table_name}\n")
            log_file.write(f"Threshold: {threshold}\n")
            log_file.write(f"Email Addresses: {', '.join(email_addresses)}\n")
            log_file.write(f"Email Content:\n{email_content}\n")
            log_file.write(f"YAML Config: {yaml_config_name}\n")

        messagebox.showinfo("Success", "Alert settings saved successfully.")
    else:
        messagebox.showerror("Error", "Please provide all necessary information.")

    # Save the updated alert_settings to a file
    save_alert_to_file()

def load_alert_settings():
    global alert_settings
    try:
        with open('alert_settings.json', 'r') as file:
            alert_settings = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        alert_settings = {}  # Initialize to empty dict if file not found or empty

# Call this function at the start of your application
load_alert_settings()

def monitor_and_send_alerts():
    try:
        with open('alert_settings.json', 'r') as file:
            alert_settings = json.load(file)
    except FileNotFoundError:
        return  # No alert settings found

    table_name = alert_settings['table_name']
    threshold = alert_settings['threshold']
    email_content = alert_settings['email_content']
    email_addresses = alert_settings['email_addresses']

    # Check the item count for the specified table
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    item_count = cursor.fetchone()[0]
    conn.close()

    if item_count < threshold:
        # Send email alert
        send_email_alert(email_addresses, f"Alert: Low item count in {table_name}", email_content)

def send_email_alert(table_name, email_addresses, yaml_config_name, email_content):
    # Load the YAML configuration
    try:
        with open(yaml_config_name, 'r') as file:
            config = yaml.safe_load(file)
            smtp_server = config['smtp_server']
            smtp_port = config['smtp_port']
            smtp_user = config['smtp_user']
            encrypted_password = config['encrypted_password'].encode()
            key = config['key'].encode()
    except FileNotFoundError:
        print("Configuration file not found. Please configure the email account.")
        return
    except KeyError:
        print("Invalid configuration file format.")
        return

    # Decrypt the password
    fernet = Fernet(key)
    decrypted_password = fernet.decrypt(encrypted_password).decode()

    # Format the table name to match the SQL naming conventions (e.g., replace spaces with underscores and lowercase)
    formatted_table_name = table_name.replace(" ", "_").lower()

    # Get the current item count for the formatted table name
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {formatted_table_name} WHERE UPPER(status) = 'OK'")
    current_count = cursor.fetchone()[0]
    conn.close()

    # Adjust the current_count for the email subject
    adjusted_count = current_count - 1

    # Extract the database name without the extension
    db_name_without_extension = os.path.splitext(os.path.basename(current_db))[0]

    # Prepare the email parameters
    to_address = email_addresses[0] if email_addresses else ""
    cc_addresses = email_addresses[1:] if len(email_addresses) > 1 else []
    cc_string = ', '.join(cc_addresses)

    # Create MIMEText object
    msg = MIMEText(email_content)
    msg['Subject'] = f"Alert: Low item count in {db_name_without_extension} - {table_name} ({adjusted_count} left)"
    msg['From'] = smtp_user
    msg['To'] = to_address
    if cc_addresses:
        msg['Cc'] = cc_string

    # Send the email
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, decrypted_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")

def send_test_email(table_combo, email_content):
    global email_addresses
    global quantity_left
    if not email_addresses:
        messagebox.showwarning("Warning", "No email addresses to send to.")
        return

    # Get the selected table name from the combobox
    selected_table_name = table_combo.get()

    # Calculate the quantity left of items with status "OK"
    quantity_left = calculate_quantity_left(selected_table_name)

    # Format the email subject and content
    subject = f"Low Level Items - {selected_table_name} ({quantity_left} left)"
    content = email_content.get("1.0", tk.END).strip()

    # Prepare the email parameters
    to_address = email_addresses[0]
    cc_addresses = email_addresses[1:] if len(email_addresses) > 1 else []
    cc_string = ','.join(cc_addresses)

    # Encode the subject and content
    encoded_subject = urllib.parse.quote(subject)
    encoded_content = urllib.parse.quote(content)

    # Construct the mailto URL
    mailto_url = f"mailto:{to_address}"
    if cc_addresses:
        mailto_url += f"?cc={cc_string}&subject={encoded_subject}&body={encoded_content}"
    else:
        mailto_url += f"?subject={encoded_subject}&body={encoded_content}"

    # Open the default email client with the mailto URL
    webbrowser.open(mailto_url)


def calculate_quantity_left(table_name):
    """Calculate the quantity of items with status 'OK' in the specified table."""
    conn = create_connection()
    cursor = conn.cursor()

    # Convert the display table name to the actual table name in the database
    db_table_name = table_name.replace(" ", "_").lower()

    cursor.execute(f"SELECT COUNT(*) FROM {db_table_name} WHERE UPPER(status) = 'OK'")
    quantity = cursor.fetchone()[0]

    conn.close()
    return quantity

def open_email_client(to_recipients, subject, content, cc_recipients=None):
    # Prepare the email parameters
    recipients = ', '.join(to_recipients)
    cc = ', '.join(cc_recipients) if cc_recipients else ''
    encoded_subject = urllib.parse.quote(subject)
    encoded_content = urllib.parse.quote(content)

    # Construct the mailto URL
    mailto_url = f"mailto:{recipients}"
    if cc:
        mailto_url += f"?cc={cc}&subject={encoded_subject}&body={encoded_content}"
    else:
        mailto_url += f"?subject={encoded_subject}&body={encoded_content}"

    # Open the default email client with the mailto URL
    webbrowser.open(mailto_url)

def open_email_alerts_window():
    global alert_tree  # Declare alert_tree as a global variable

    # Create a new top-level window
    alerts_window = tk.Toplevel(root)
    alerts_window.title("Email Alerts")
    alerts_window.iconbitmap("icons.ico")

    # Create a Treeview to display the alert settings
    alert_tree = ttk.Treeview(alerts_window, columns=("Table", "Threshold", "SMTP Config", "Email Addresses"), show="headings")
    alert_tree.heading("Table", text="Table")
    alert_tree.heading("Threshold", text="Threshold")
    alert_tree.heading("SMTP Config", text="SMTP Config")  # Rename the column to "YAML Config"
    alert_tree.heading("Email Addresses", text="Email Addresses")
    alert_tree.pack(fill=tk.BOTH, expand=True)

    # Populate the Treeview with the alert settings
    for table_name, settings in alert_settings.items():
        email_addresses = ', '.join(settings["email_addresses"])
        yaml_config_name = settings.get("yaml_config_name", "N/A")  # Use "N/A" if yaml_config_name is not available
        alert_tree.insert('', 'end', values=(table_name, settings["threshold"], yaml_config_name, email_addresses))

    # Bind the BackSpace key to delete_selected_alerts function
    alert_tree.bind("<BackSpace>", lambda event: delete_selected_alerts())

    # Function to handle double-click event on the Treeview
    def on_double_click(event):
        selected_item = alert_tree.selection()
        if not selected_item:
            return

        # Retrieve the alert details
        selected_alert = alert_tree.item(selected_item, 'values')
        table_name, threshold, smtp_config, recipients = selected_alert

        # Open the Warning Level Window with pre-filled data
        open_warning_level_window(pre_fill_data=(table_name, threshold, smtp_config, recipients))

    # Bind double-click event
    alert_tree.bind("<Double-1>", on_double_click)

def save_favorite_email_content(content):
    file_name = simpledialog.askstring("Save Favorite Content", "Enter a name for the saved content:")
    if file_name and content.strip():
        file_path = os.path.join(os.path.dirname(__file__), f"{file_name}.txt")
        with open(file_path, "w") as file:
            file.write(content)
    update_saved_content_combobox(saved_content_combo)

def update_saved_content_combobox(combo):
    saved_files = [f[:-4] for f in os.listdir(os.path.dirname(__file__)) if f.endswith('.txt')]
    combo['values'] = saved_files

def load_favorite_email_content(file_name, textbox):
    file_path = os.path.join(os.path.dirname(__file__), f"{file_name}.txt")
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            content = file.read()
            textbox.delete("1.0", tk.END)
            textbox.insert(tk.END, content)

def save_modified_email_content(selected_content_name, content):
    if not selected_content_name or selected_content_name == "Select Mail Content":
        messagebox.showwarning("Warning", "Please select a mail content to modify.")
        return

    # Determine the file path
    file_path = os.path.join(os.path.dirname(__file__), f"{selected_content_name}.txt")

    # Save the modified content to the file
    try:
        with open(file_path, 'w') as file:
            file.write(content)
        messagebox.showinfo("Success", f"Content modified and saved to '{selected_content_name}.txt'")
    except Exception as e:
        messagebox.showerror("Error", f"Error saving modified content: {e}")

def delete_selected_email_content_file(event=None):
    selected_content_name = saved_content_combo.get()
    if not selected_content_name or selected_content_name == "Select Mail Content":
        messagebox.showwarning("Warning", "Please select a mail content to delete.")
        return

    # Confirm deletion
    confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the file '{selected_content_name}.txt'?")
    if not confirm:
        return

    # Determine the file path
    file_path = os.path.join(os.path.dirname(__file__), f"{selected_content_name}.txt")

    # Delete the file
    try:
        os.remove(file_path)
        messagebox.showinfo("Success", f"Content file '{selected_content_name}.txt' deleted successfully.")
        update_saved_content_combobox(saved_content_combo)  # Update combobox values
    except Exception as e:
        messagebox.showerror("Error", f"Error deleting content file: {e}")

def delete_selected_alerts():
    global alert_settings  # Access the global alert settings dictionary

    selected_items = alert_tree.selection()
    if selected_items:
        for item in selected_items:
            # Get the table name from the selected item
            table_name = alert_tree.item(item, 'values')[0]

            # Remove the item from the alert settings and the Treeview
            if table_name in alert_settings:
                del alert_settings[table_name]
                alert_tree.delete(item)

        # Save the updated alert settings to the JSON file
        with open('alert_settings.json', 'w') as file:
            json.dump(alert_settings, file, indent=4)

def send_summary_email(event=None):
    # Gather quantities of "OK" items from all tables
    table_quantities = []
    conn = create_connection()
    cursor = conn.cursor()
    for table_name in category_fields.keys():
        formatted_table_name = table_name.replace(" ", "_").lower()
        cursor.execute(f"SELECT COUNT(*) FROM {formatted_table_name} WHERE UPPER(status) = 'OK'")
        count = cursor.fetchone()[0]
        table_quantities.append(f"{table_name} - {count} left")

    # Construct the email content
    content = "\n".join(table_quantities)

    # Extract the database name without the extension
    db_name_without_extension = os.path.splitext(os.path.basename(current_db))[0]

    # Get the current timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")

    # Format the email subject
    subject = f"Current Stock Situation {db_name_without_extension} {timestamp}"

    # Check if there are email addresses to send to
    if email_addresses:
        # Use the first email address as the recipient and the rest as CC (if any)
        recipient = email_addresses[0]
        cc_recipients = email_addresses[1:]
        open_email_client([recipient], subject, content, cc_recipients)
    else:
        messagebox.showwarning("Warning", "No email addresses to send to.")

def list_yaml_files():
    """List all YAML files in the current directory."""
    return [f for f in os.listdir('.') if f.endswith('.yaml')]

def load_yaml_config(file_name):
    """Load YAML configuration from a file."""
    with open(file_name, 'r') as file:
        return yaml.safe_load(file)

def save_yaml_config(file_name, data):
    """Save YAML configuration to a file."""
    with open(file_name, 'w') as file:
        yaml.dump(data, file)

def open_email_config_window():
    """Open a window to configure and save email settings."""
    config_window = tk.Toplevel(root)
    config_window.title("Configure Email Account")
    config_window.iconbitmap("icons.ico")

    # Combobox for selecting YAML configuration files
    config_files_combo = ttk.Combobox(config_window, values=list_yaml_files())
    config_files_combo.grid(row=0, column=0, columnspan=2, padx=10, pady=5)

    # Entry fields for SMTP configuration
    smtp_server_entry = ttk.Entry(config_window)
    smtp_server_entry.grid(row=1, column=1, padx=10, pady=5)
    ttk.Label(config_window, text="SMTP Server:", background="#F0F0F0").grid(row=1, column=0)

    smtp_port_entry = ttk.Entry(config_window)
    smtp_port_entry.grid(row=2, column=1, padx=10, pady=5)
    ttk.Label(config_window, text="SMTP Port:", background="#F0F0F0").grid(row=2, column=0)

    smtp_user_entry = ttk.Entry(config_window)
    smtp_user_entry.grid(row=3, column=1, padx=10, pady=5)
    ttk.Label(config_window, text="SMTP User:", background="#F0F0F0").grid(row=3, column=0)

    smtp_password_entry = ttk.Entry(config_window, show='*')
    smtp_password_entry.grid(row=4, column=1, padx=10, pady=5)
    ttk.Label(config_window, text="SMTP Password:", background="#F0F0F0").grid(row=4, column=0)

    # Function to update entry fields when a config file is selected
    def update_fields(event):
        selected_file = config_files_combo.get()
        if selected_file:
            config = load_yaml_config(selected_file)
            smtp_server_entry.delete(0, tk.END)
            smtp_port_entry.delete(0, tk.END)
            smtp_user_entry.delete(0, tk.END)
            smtp_password_entry.delete(0, tk.END)
            smtp_server_entry.insert(0, config.get('smtp_server', ''))
            smtp_port_entry.insert(0, config.get('smtp_port', ''))
            smtp_user_entry.insert(0, config.get('smtp_user', ''))
            # Password is encrypted, so we cannot display it

    config_files_combo.bind("<<ComboboxSelected>>", update_fields)

    # Function to save the SMTP configuration
    def save_config():
        smtp_server = smtp_server_entry.get()
        smtp_port = smtp_port_entry.get()
        smtp_user = smtp_user_entry.get()
        password = smtp_password_entry.get()

        # Encrypt the password
        key = Fernet.generate_key()
        fernet = Fernet(key)
        encrypted_password = fernet.encrypt(password.encode()).decode()

        # Save the configuration
        file_name = simpledialog.askstring("Save Configuration", "Enter file name for the configuration:")
        if file_name:
            save_yaml_config(f"{file_name}.yaml", {
                'smtp_server': smtp_server,
                'smtp_port': smtp_port,
                'smtp_user': smtp_user,
                'encrypted_password': encrypted_password,
                'key': key.decode()
            })
            config_files_combo['values'] = list_yaml_files()  # Update the combobox list

    ttk.Button(config_window, text="Save Configuration", command=save_config).grid(row=5, column=0, columnspan=2, padx=10, pady=10)

def open_link(url):
    webbrowser.open_new(url)

def about():
    about_window = tk.Toplevel(root)
    about_window.title("About")
    about_window.iconbitmap("icons.ico")
    about_window.geometry("400x300")  # Adjust the size as needed
    about_window.resizable(0,0)

    # Load the background image
    image_path = "donkey.png"
    bg_image = Image.open(image_path)
    bg_image = bg_image.resize((400, 300), Image.Resampling.LANCZOS)  # Resize to fit the window
    bg_photo = ImageTk.PhotoImage(bg_image)

    # Create a label to display the image
    bg_label = tk.Label(about_window, image=bg_photo)
    bg_label.image = bg_photo  # Keep a reference to avoid garbage collection
    bg_label.place(x=0, y=0, relwidth=1, relheight=1)

    # Load icon images
    email_icon = ImageTk.PhotoImage(Image.open("email.png").resize((30, 30), Image.Resampling.LANCZOS))
    linkedin_icon = ImageTk.PhotoImage(Image.open("lk.png").resize((30, 30), Image.Resampling.LANCZOS))
    github_icon = ImageTk.PhotoImage(Image.open("gh.png").resize((30, 30), Image.Resampling.LANCZOS))

    # Labels' text
    author_text = "Author: DUTHIL Jonathan\nFirst Release: 1/2/24"
    email_text = "j.duthil@outlook.fr"
    linkedin_url = "https://linkedin.com/in/jonathanduthil"
    github_url = "https://github.com/gelndjj"

    # Background color for labels
    bg_color = "#ffffff"  # Adjust to match your background image

    # Create author label
    author_label = tk.Label(about_window, text=author_text, fg="black", bg=bg_color)
    author_label.place(x=5, y=300, anchor="sw")

    # Create icon buttons
    email_button = tk.Button(about_window, image=email_icon, bg=bg_color, borderwidth=0,
                             command=lambda: webbrowser.open(f"mailto:{email_text}?subject=About: CokEnStok APP"))
    linkedin_button = tk.Button(about_window, image=linkedin_icon, bg=bg_color, borderwidth=0,
                                command=lambda: webbrowser.open(linkedin_url))
    github_button = tk.Button(about_window, image=github_icon, bg=bg_color, borderwidth=0,
                              command=lambda: webbrowser.open(github_url))

    # Keep a reference to avoid garbage collection
    email_button.image = email_icon
    linkedin_button.image = linkedin_icon
    github_button.image = github_icon

    # Place icon buttons in specific areas (adjust x, y as needed)
    email_button.place(x=5, y=20, anchor="nw")
    linkedin_button.place(x=5, y=70, anchor="nw")
    github_button.place(x=5, y=120, anchor="nw")

def open_keyboard_shortcuts_window():
    # Create a new top-level window
    shortcuts_window = tk.Toplevel(root)
    shortcuts_window.title("Keyboard Shortcuts")
    shortcuts_window.iconbitmap("icons.ico")

    # Create a Text widget to display the keyboard shortcuts
    text_widget = tk.Text(shortcuts_window, wrap='word')
    text_widget.pack(fill='both', expand=True)

    # List of keyboard shortcuts and their descriptions
    keyboard_shortcuts = [
        ("<BackSpace>", "Delete selected email(s)", "Address Book Window"),
        ("<BackSpace>", "Delete selected email(s)", "Email Alerts Window"),
        ("<Control-BackSpace>", "Delete selected email content file", "Warning Level Settings Window"),
        ("<Control-Shift-S>", "Send summary email", "Warning Level Settings Window"),
        ("<Control-a>", "Select all items in the tree", "Main Window"),
        ("<Control-f>", "Open search window", "Main Window"),
        ("<Control-Down>", "Switch to next theme", "Main Window"),
        ("<Control-Up>", "Switch to previous theme", "Main Window"),
        ("<Control-r>", "Refresh the GUI", "Main Window"),
        ("<Control-w>", "Open Warning Level Settings", "Main Window"),
        ("<Control-e>", "Open Graphic Menu", "Main Window"),
        ("<Control-s>", "Open Snitch Window", "Main Window"),
        ("<Control-i>", "Open About Window", "Main Window"),
        ("<Control-k>", "Open Keyboard Shortcuts Window", "Main Window"),
        ("<Control-u>", "Configure Email Account", "Main Window"),
        ("<Button-2>", "Open tab context menu (UNIX)", "Main Window"),
        ("<Button-3>", "Open tab context menu (WINDOWS)", "Main Window"),
        ("<Control-Shift-Right>", "Select Next Database", "Database Menu"),
        ("<Control-Shift-Left>", "Select Previous Database", "Database Menu"),
        ("<Control-Shift-C>", "Create Database", "Database Menu"),
        ("<Control-Shift-A>", "Add Table", "Database Menu"),
        ("<Control-Shift-BackSpace>", "Wipe Out Database", "Tools Menu"),
        ("<Control-Shift-B>", "Backup Database", "Tools Menu"),
        ("<Control-Shift-N>", "Start as New Database", "Tools Menu"),
        # Add more shortcuts here
    ]

    # Format and insert the keyboard shortcuts into the Text widget
    for shortcut, description, context in keyboard_shortcuts:
        text_widget.insert(tk.END, f"Shortcut: {shortcut}\nDescription: {description}\nContext: {context}\n\n")

    # Make the Text widget read-only
    text_widget.config(state='disabled')

def add_email_address_book(email_tree, email):
    if email and "@" in email:  # Basic validation for email format
        email_tree.insert('', 'end', values=(email,))

def add_email_from_address_book(email_tree, email_addresses):
    # Add each email to the tree
    for email in email_addresses:
        add_email(email_tree, email)  # Assuming 'add_email' adds the email to the tree

    # Extract the updated email addresses from the tree
    updated_email_addresses = [email_tree.item(item_id, 'values')[0] for item_id in email_tree.get_children()]

    # Save the updated email addresses
    save_email_addresses(updated_email_addresses)

def manage_address_book(email_tree):
    global address_book_tree
    address_book_window = tk.Toplevel(root)
    address_book_window.title("Address Book")
    address_book_window.iconbitmap("icons.ico")
    address_book_window.geometry("300x400")

    # Load existing addresses from the address book file
    try:
        with open("address_book.json", "r") as file:
            addresses = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        addresses = []

    # Treeview for address book
    address_book_tree = ttk.Treeview(address_book_window, columns=('Email'), show='headings')
    address_book_tree.heading('Email', text='Email Address')
    address_book_tree.pack(fill=tk.BOTH, expand=True)

    # Populate the treeview
    for email in addresses:
        address_book_tree.insert('', 'end', values=(email,))

    # Entry field for new email address
    email_entry = ttk.Entry(address_book_window)
    email_entry.pack(pady=5)

    def add_email_to_address_book():
        email = email_entry.get()
        if email and "@" in email:
            addresses.append(email)
            address_book_tree.insert('', 'end', values=(email,))
            email_entry.delete(0, tk.END)
            with open("address_book.json", "w") as file:
                json.dump(addresses, file)

    # Button to add new email address to address book
    add_button = ttk.Button(address_book_window, text="Add Email to Address Book", command=add_email_to_address_book)
    add_button.pack(pady=5)

    # Button to select emails from address book and add to warning level settings
    select_button = ttk.Button(address_book_window, text="Add Selected Emails to Alert",
                               command=lambda: add_email_from_address_book(email_tree,
                                                                           [address_book_tree.item(item, 'values')[0]
                                                                            for item in address_book_tree.selection()]))
    select_button.pack(pady=5)

    def delete_selected_email_addbook(event=None):
        selected_items = address_book_tree.selection()
        if not selected_items:
            return  # No item selected

        for item in selected_items:
            email = address_book_tree.item(item, 'values')[0]
            addresses.remove(email)  # Remove from the list
            address_book_tree.delete(item)  # Remove from Treeview

        # Update the JSON file
        with open("address_book.json", "w") as file:
            json.dump(addresses, file)

    # Bind Backspace key to delete selected email(s)
    address_book_tree.bind("<BackSpace>", delete_selected_email_addbook)
def clear_stats_current_table():
    current_tab = notebook.tab(notebook.select(), "text")
    if current_tab == "Overview":
        messagebox.showwarning("Warning", "Cannot clear stats for the Overview tab.")
        return

    formatted_table_name = current_tab.replace(" ", "_").lower()
    confirm = messagebox.askyesno("Clear Stats", f"Are you sure you want to clear stats for the '{current_tab}' table?")
    if not confirm:
        return

    try:
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM item_transactions WHERE table_name = ?", (formatted_table_name,))
        conn.commit()
        messagebox.showinfo("Success", f"Stats for the '{current_tab}' table have been cleared.")
    except Exception as e:
        messagebox.showerror("Error", f"Error clearing stats: {e}")
    finally:
        conn.close()

# Initialize the themed main window
root = ThemedTk(theme="clearlooks")
root.title("CokEnStok")
root.iconbitmap("icons.ico")

# Initialize ThemedStyle
style = ThemedStyle(root)
# style.configure('.', font=('Segoe UI', 10))

# Create a menu bar
menu_bar = tk.Menu(root)
root.config(menu=menu_bar)

# Create a menu for themes
theme_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Themes", menu=theme_menu)

# Add database menu to the menu bar
database_menu = tk.Menu(menu_bar, tearoff=0)
stats_menu = tk.Menu(menu_bar, tearoff=0)
tools_menu = tk.Menu(menu_bar, tearoff=0)
help_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Database", menu=database_menu)
menu_bar.add_cascade(label="Statistics", menu=stats_menu)
menu_bar.add_cascade(label="Tools", menu=tools_menu)
menu_bar.add_cascade(label="Help", menu=help_menu)

# Add submenus to the database menu
database_menu.add_command(label="Browse Database (.db)", command=browse_and_copy_databases)
database_menu.add_command(label="Create Database", command=create_database)
select_db_menu = tk.Menu(database_menu, tearoff=0)
create_database_submenu()
database_menu.add_separator()
database_menu.add_command(label="Save Full Database (.zip)", command=save_online_database)
database_menu.add_command(label="Browse Full Database (.zip)", command=browse_online_database)
create_database_submenu()
database_menu.add_separator()
database_menu.add_command(label="Edit Database", command=Edit_Database)
database_menu.add_cascade(label="Select Database", menu=select_db_menu)
create_database_submenu()  # Populate the submenu
database_menu.add_command(label="Backup Database", command=backup_database)
database_menu.add_separator()
database_menu.add_command(label="Export Current Table to CSV", command=export_current_table_to_csv)
database_menu.add_command(label="Export Full Database to XLS", command=export_db_to_excel)
database_menu.add_separator()
database_menu.add_command(label="Clear Current Table Items", command=clear_current_table)
database_menu.add_command(label="Clear Full Database Items", command=clear_database)
database_menu.add_separator()
database_menu.add_command(label="Wipe Out Database", command=wipe_current_database)
database_menu.add_separator()
database_menu.add_command(label="Rollback Last Table Deleted", command=rollback_last_delete)

stats_menu.add_command(label="Graphic Evolution", command=open_evolution_window)
stats_menu.add_command(label="Snitch Log", command=open_snitch_window)

tools_menu.add_command(label="Start as New Database", command=start_as_new_database)
tools_menu.add_separator()
tools_menu.add_command(label="Warning Level Settings", command=open_warning_level_window)
tools_menu.add_command(label="Configure Email Account", command=open_email_config_window)
tools_menu.add_separator()
tools_menu.add_command(label="Clear Stats Current Table", command=clear_stats_current_table)


help_menu.add_command(label="About", command=about)
help_menu.add_separator()
help_menu.add_command(label="Keyboard Shortcuts", command=open_keyboard_shortcuts_window)


# Initialize a label to display the current database
current_db_label = tk.Label(root, text=f"Current DB: {current_db}")
current_db_label.pack(side=tk.TOP, fill=tk.X)

# List of available themes
themes = ['breeze', 'arc', 'adapta', 'aqua', 'black', 'blue', 'clearlooks', 'elegance', 'equilux', 'keramik',
          'kroc', 'plastik', 'radiance', 'scidgrey', 'scidmint', 'scidpink', 'scidsand', 'smog', 'ubuntu',
          'winxpblue']

# Add themes to the theme menu
for theme in themes:
    theme_menu.add_command(label=theme, command=lambda t=theme: change_theme(t))

# Create the notebook (tab container)
notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True)

category_fields = {
    "Computer": ["Brand", "Model", "Owner", "Serial", "Status"],
    "Smartphone": ["Brand", "Model", "Serial", "Status"],
    "Tablet": ["Brand", "Model", "Serial", "Status"],
    "Headset": ["Brand", "Model", "Status"],
    "Keyboard": ["Brand", "Layout", "Status"],
    "Mouse": ["Brand", "Status"],
    "Bag": ["Brand", "Type", "Status"],
    "Dock Station": ["Brand", "Watt", "Status"],
    "Screen": ["Brand", "Size", "Status"],
    "SIM": ["Carrier", "Status"],
    "Privacy Screen": ["Brand", "Size", "Status"],
    "Smartphone Case": ["Brand", "Compatible", "Status"],
    "Smartphone Charger": ["Brand", "Connection", "Status"],
    "Laptop Charger": ["Brand", "Connection", "Watt","Status"]
}

# Now call create_tables
create_tables()

def add_batch_items(category, entries, batch_entry):
    try:
        batch_count = int(batch_entry.get())
        if batch_count <= 0:
            raise ValueError("Number must be positive")
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid positive integer")
        return

    # Capture the current values from the entries
    current_values = [entry.get() for entry in entries]

    for _ in range(batch_count):
        # Set the entries to the captured values for each item in the batch
        for entry, value in zip(entries, current_values):
            if isinstance(entry, ttk.Combobox):
                entry.set(value)
            else:
                entry.delete(0, tk.END)
                entry.insert(0, value)

        # Add the item to the database
        add_item(category, entries)

    # Clear the entries and refresh the list
    for entry in entries:
        if isinstance(entry, ttk.Combobox):
            entry.set('')  # Clear Combobox
        else:
            entry.delete(0, tk.END)  # Clear Entry
    populate_list(category)
    update_overview()

# Function to create a tab with the given fields
def create_tab(category, fields):
    paned_window = ttk.PanedWindow(notebook, orient='horizontal')
    notebook.add(paned_window, text=category)

    left_frame = ttk.Frame(paned_window)
    paned_window.add(left_frame, weight=1)

    right_frame = ttk.Frame(paned_window)
    paned_window.add(right_frame, weight=3)

    entries = []

    # Place ComboBoxes in two columns on the left side
    for i, field in enumerate(fields):
        row = i // 2  # 2 ComboBoxes per column
        col = i % 2  # Column index will be 0 or 1
        values = fetch_distinct_values(field.lower(), category)
        combo = ttk.Combobox(left_frame, values=values, width=20)
        combo.set(field)  # Set default value as field name
        combo._name = field.lower()
        combo.grid(row=row, column=col, padx=5, pady=5, sticky='ew')
        combo.bind("<FocusIn>", on_focus_in)
        combo.bind("<FocusOut>", on_focus_out)
        entries.append(combo)

        combo.bind("<<ComboboxSelected>>",
                   lambda event, cat=category, f=field.lower(), cb=combo: on_combobox_select(event, cat, f, cb))

    # Place buttons after the ComboBoxes
    button_row = len(fields) // 2 if len(fields) % 2 == 0 else len(fields) // 2 + 1

    # Add and Edit buttons
    add_button = ttk.Button(left_frame, text="Add Item", command=lambda: add_item(category, entries))
    add_button.grid(row=button_row, column=0, padx=5, pady=5, sticky='ew')

    edit_button = ttk.Button(left_frame, text="Edit Item", command=lambda: edit_item(category, entries))
    edit_button.grid(row=button_row, column=1, padx=5, pady=5, sticky='ew')

    # Delete and Clear buttons on the next row
    delete_button = ttk.Button(left_frame, text="Delete Item", command=lambda: delete_item(category, entries))
    delete_button.grid(row=button_row + 1, column=0, padx=5, pady=5, sticky='ew')

    # Create "Add Batch Items" button
    add_batch_button = ttk.Button(left_frame, text="Add Batch Items",
                                  command=lambda: add_batch_items(category, entries, batch_entry))
    add_batch_button.grid(row=button_row + 2, column=0, padx=5, pady=5, sticky='ew')

    clear_button = ttk.Button(left_frame, text="Clear Fields",
                              command=lambda: clear_fields_and_update(category, entries, tabs[category]['tree']))
    clear_button.grid(row=button_row + 1, column=1, padx=5, pady=5, sticky='ew')

    # Create Entry for specifying number of items to add in batch
    batch_entry = ttk.Entry(left_frame, width=20)
    batch_entry.grid(row=button_row + 2, column=1, padx=5, pady=5, sticky='ew')
    batch_entry.insert(0, '1')  # Default value

    # Record count label on the next row
    record_count_label = ttk.Label(left_frame, text="Records: 0")
    record_count_label.grid(row=button_row + 3, column=0, columnspan=2, padx=5, pady=5, sticky='ew')

    tabs[category]['record_count_label'] = record_count_label

    # Apply on_focus_in event to each entry in the left frame
    for entry in left_frame.winfo_children():
        if isinstance(entry, ttk.Entry) or isinstance(entry, ttk.Combobox):
            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)

    # Create and configure the Treeview in the right frame
    tree = ttk.Treeview(right_frame, columns=('ID', *fields), show='headings')
    tree.column('ID', width=0, stretch=tk.NO, anchor='center')  # Hide the ID column

    for field in fields:
        tree.heading(field, text=field)
        tree.column(field, anchor='center', width=100)  # Adjust width as needed
    tree.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

    tree.bind("<<TreeviewSelect>>", lambda event, c=category: on_tree_select(event, c))
    tree.bind('<KeyRelease>', lambda event, c=category: on_key_release(event, c))
    tree.bind('<Control-a>', lambda event, t=tree: select_all(t))  # Bind Ctrl+A

    # Make the right frame fill the remaining space
    right_frame.grid_rowconfigure(0, weight=1)
    right_frame.grid_columnconfigure(0, weight=1)

    # Store widgets in tabs dictionary
    tabs[category].update({'frame': paned_window, 'entries': entries, 'tree': tree, 'record_count_label': record_count_label})

    return paned_window

# Create the tabs for different categories
tabs = {category: {'frame': None, 'entries': None, 'tree': None, 'record_count_label': None} for category in category_fields}
for category, fields in category_fields.items():
    tab = create_tab(category, fields)

create_overview_tab()  # Create the Overview tab

# Function to update the Treeview based on the selected tab
def on_tab_selected(event):
    selected_tab = event.widget.select()
    tab_text = event.widget.tab(selected_tab, "text")
    if tab_text == "Overview":
        update_overview()  # Update the Overview tab
    else:
        populate_list(tab_text)  # Update other category tabs


def edit_item(category, entries):
    table_name = category.replace(" ", "_").lower()
    entry_values = [entry.get().strip() for entry in entries if isinstance(entry, (ttk.Combobox, tk.Entry))]

    # Check if at least one row is selected
    tree = tabs[category]['tree']
    selected_items = tree.selection()
    if not selected_items:
        messagebox.showinfo("Edit Item", "No item selected for editing.")
        return

    conn = create_connection()
    cursor = conn.cursor()

    # Fetch the fields for the current category
    fields = category_fields[category]
    fields_lower = [field.lower().replace(' ', '_') for field in fields]

    # Construct the SQL query dynamically
    update_fields = [f"{field} = ?" for field in fields_lower]
    sql_update = ", ".join(update_fields)

    # Loop through each selected item and update it in the database
    for item in selected_items:
        item_id = tree.item(item, 'values')[0]
        sql_query = f"UPDATE {table_name} SET {sql_update} WHERE id = ?"
        cursor.execute(sql_query, (*entry_values, item_id))

    conn.commit()
    conn.close()
    populate_list(category)
    update_overview()

    # Clear the entries after updating
    for entry in entries:
        if isinstance(entry, (ttk.Combobox, tk.Entry)):
            entry.set('') if isinstance(entry, ttk.Combobox) else entry.delete(0, tk.END)

def calculate_current_count(table_name):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE UPPER(status) = 'OK'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def check_and_send_alerts(table_name):
    global alert_settings
    current_count = calculate_current_count(table_name)

    # Check if the table has an alert setting and if the current count has reached the threshold
    if table_name in alert_settings and current_count <= alert_settings[table_name]['threshold']:
        email_content = alert_settings[table_name]['email_content']
        email_addresses = alert_settings[table_name]['email_addresses']
        yaml_config_name = alert_settings[table_name].get('yaml_config_name')

        # Update the email content with the correct current count
        email_content = email_content.replace("{current_count}", str(current_count))

        # Send the email alert
        send_email_alert(table_name, email_addresses, yaml_config_name, email_content)

def delete_item(category, entries):
    # Access the tree widget from the tabs dictionary for the given category
    tree = tabs[category]['tree']

    selected_items = tree.selection()
    if not selected_items:
        return  # No item selected

    # Format the table name to match the SQL naming conventions
    formatted_table_name = category.replace(" ", "_").lower()
    check_and_send_alerts(formatted_table_name)

    conn = create_connection()
    cursor = conn.cursor()

    for item in selected_items:
        id_value = tree.item(item, 'values')[0]

        # Fetch the details of the item before deleting
        cursor.execute(f"SELECT * FROM {formatted_table_name} WHERE id = ?", (id_value,))
        item_details = cursor.fetchone()

        # Delete the item
        cursor.execute(f"DELETE FROM {formatted_table_name} WHERE id = ?", (id_value,))
        tree.delete(item)

        # Log the deletion
        log_transaction(conn, formatted_table_name, 'delete')

        # Log action to JSON (for Snitch functionality)
        if item_details:
            log_action_to_json(current_db, "delete", {"table": formatted_table_name, "deleted_item": item_details})

    conn.commit()
    conn.close()

    # Refresh the tree view to reflect the deletion
    populate_list(category)

def open_search_window():
    search_window = tk.Toplevel(root)
    search_window.title("Search")
    search_window.iconbitmap("icons.ico")

    # Category selection ComboBox
    category_label = ttk.Label(search_window, text="Select Category:")
    category_label.pack(padx=10, pady=5)

    category_var = tk.StringVar()
    category_combo = ttk.Combobox(search_window, textvariable=category_var, values=list(category_fields.keys()))
    category_combo.pack(padx=10, pady=5)

    search_label = ttk.Label(search_window, text="Enter search term:")
    search_label.pack(padx=10, pady=5)

    search_var = tk.StringVar()
    search_entry = ttk.Entry(search_window, textvariable=search_var)
    search_entry.pack(padx=10, pady=5)
    search_entry.focus()

    # Treeview for search results
    columns = ('ID', 'Category', 'Brand', 'Model', 'Owner', 'Serial', 'Status')
    search_tree = ttk.Treeview(search_window, columns=columns, show='headings')
    for col in columns:
        search_tree.heading(col, text=col)
        search_tree.column(col, anchor='center')
    search_tree.pack(fill='both', expand=True)

    # Set up tracing on the search variable and category selection
    search_var.trace_add('write', lambda *args: perform_search(*args))
    category_var.trace_add('write', lambda *args: perform_search(*args))

    def perform_search(*args):
        search_term = search_var.get().lower()
        selected_category = category_var.get()
        if selected_category:
            results = search_in_category(selected_category, search_term)
            update_search_results(results, selected_category)

    def search_in_category(category, search_term):
        table_name = category.replace(" ", "_").lower()
        conn = create_connection()
        cursor = conn.cursor()

        # Construct a dynamic query for the selected category
        select_fields = ['id'] + [field.lower().replace(' ', '_') for field in category_fields[category]]
        select_statement = ', '.join(select_fields)

        query = f"SELECT {select_statement} FROM {table_name} WHERE " + ' OR '.join(
            [f"{field} LIKE ?" for field in select_fields])
        cursor.execute(query, tuple(['%' + search_term + '%'] * len(select_fields)))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def update_search_results(results, category):
        search_tree.delete(*search_tree.get_children())

        # Define columns based on the selected category
        fields = ['ID'] + category_fields[category]
        search_tree['columns'] = fields

        # Configure column headings and columns
        for field in fields:
            search_tree.heading(field, text=field)
            search_tree.column(field, anchor='center')

        for row in results:
            search_tree.insert('', 'end', values=row)

def search_in_all_records(search_term):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category, brand, model, owner, serial, status
        FROM items
        WHERE LOWER(category) LIKE ? OR LOWER(brand) LIKE ? OR
              LOWER(model) LIKE ? OR LOWER(owner) LIKE ? OR
              LOWER(serial) LIKE ? OR LOWER(status) LIKE ?
    """, tuple(['%' + search_term + '%']*6))
    rows = cursor.fetchall()
    conn.close()
    return rows

def next_theme():
    current_theme_index = themes.index(style.theme_use())
    next_theme_index = (current_theme_index + 1) % len(themes)
    change_theme(themes[next_theme_index])

def previous_theme():
    current_theme_index = themes.index(style.theme_use())
    previous_theme_index = (current_theme_index - 1) % len(themes)
    change_theme(themes[previous_theme_index])

# Bind the tab selected event
notebook.bind("<<NotebookTabChanged>>", on_tab_selected)

def load_last_used_db():
    try:
        with open("last_db.txt", "r") as file:
            db_name = file.read().strip()
            if db_name and os.path.exists(db_name):
                global current_db, category_fields
                current_db = db_name

                # Load category fields from the JSON file
                category_fields = load_category_fields_from_json(db_name)

                # Update UI to reflect the newly loaded database
                update_ui()

                # Additional steps to mimic select_database behavior, if needed
                current_db_label.config(text=f"Current DB: {db_name}")  # Update the label
                for category in category_fields:
                    populate_list(category)
    except FileNotFoundError:
        pass  # File not found, ignore
    except Exception as e:
        print(f"Error loading last used database: {e}")
    refresh_gui()

def ensure_item_transactions_table_exists():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            transaction_type TEXT,
            transaction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def delete_table(table_name):
    global deleted_tables
    # Enclose the table name in double quotes
    safe_table_name = f'"{table_name}"'
    deleted_table_name = f"deleted_{table_name}"

    confirm = messagebox.askyesno("Delete Table", f"Are you sure you want to delete the table '{table_name}'?")
    if not confirm:
        return

    try:
        with sqlite3.connect(current_db) as conn:
            cursor = conn.cursor()
            # Rename the table with a "deleted_" prefix before dropping
            cursor.execute(f"ALTER TABLE {safe_table_name} RENAME TO \"{deleted_table_name}\";")
            conn.commit()

        # Store the deleted table's information in deleted_tables
        deleted_tables[table_name] = (deleted_table_name, category_fields[table_name])

        # Remove the table from category_fields
        if table_name in category_fields:
            del category_fields[table_name]

        # Save the updated category_fields to the JSON file
        save_category_fields_to_json(current_db, category_fields)

        # Update the UI
        update_ui()

        # messagebox.showinfo("Success", f"Table '{table_name}' deleted successfully.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error deleting table '{table_name}': {e}")

def duplicate_table(table_name):
    new_table_name = simpledialog.askstring("Duplicate Table", "Enter the name for the duplicate table:")
    if not new_table_name:
        return

    safe_table_name = table_name.replace(" ", "_")
    safe_new_table_name = new_table_name.strip().lower().replace(" ", "_")

    safe_table_name_quoted = f'"{safe_table_name}"'
    safe_new_table_name_quoted = f'"{safe_new_table_name}"'

    try:
        with sqlite3.connect(current_db) as conn:
            cursor = conn.cursor()

            # Get the column structure of the original table
            cursor.execute(f"PRAGMA table_info({safe_table_name_quoted});")
            columns_info = cursor.fetchall()
            columns_definition = ", ".join([f"{col[1]} {col[2]}" for col in columns_info])

            # Create the new table with the same column structure but no data
            cursor.execute(f"CREATE TABLE {safe_new_table_name_quoted} ({columns_definition});")

        formatted_new_table_name = format_table_name_for_display(new_table_name)
        category_fields[formatted_new_table_name] = [col[1] for col in columns_info if col[1].lower() != 'id']
        save_category_fields_to_json(current_db, category_fields)
        update_ui()
        refresh_tree(formatted_new_table_name)

        messagebox.showinfo("Success", f"Table '{table_name}' duplicated as '{formatted_new_table_name}' successfully.")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Error duplicating table '{table_name}': {e}")

def refresh_tree(category):
    # Access the tree widget from the tabs dictionary for the given category
    tree = tabs[category]['tree']

    # Clear the existing entries in the tree
    tree.delete(*tree.get_children())

    # Repopulate the tree with data from the database
    populate_list(category)

def on_tab_right_click(event, notebook):
    # Get the tab index under the cursor
    tab_index = notebook.index("@%d,%d" % (event.x, event.y))
    tab_text = notebook.tab(tab_index, "text")

    # Create a popup menu
    popup_menu = tk.Menu(notebook, tearoff=0)
    popup_menu.add_command(label="Add New Column (New Field)", command=lambda: add_new_column(tab_text))
    popup_menu.add_separator()
    popup_menu.add_command(label="Delete Table", command=lambda: delete_table(tab_text))
    popup_menu.add_command(label="Duplicate Table", command=lambda: duplicate_table(tab_text))
    popup_menu.add_separator()
    popup_menu.add_command(label="Move Tab Left", command=lambda: move_tab_left(tab_text))
    popup_menu.add_command(label="Move Tab Right", command=lambda: move_tab_right(tab_text))
    popup_menu.add_separator()
    popup_menu.add_command(label="Move Tab Left -5", command=lambda: move_tab(tab_index, tab_index - 5))
    popup_menu.add_command(label="Move Tab Right +5", command=lambda: move_tab(tab_index, tab_index + 5))

    # Disable "Add New Column (New Field)" for the Overview tab
    if tab_text == "Overview":
        popup_menu.entryconfig("Add New Column (New Field)", state="disabled")

    # Display the popup menu
    try:
        popup_menu.tk_popup(event.x_root, event.y_root)
    finally:
        popup_menu.grab_release()

def move_tab(old_index, new_index):
    global category_fields  # Declare the global variable at the start of the function

    # Get the list of categories and move the selected category
    categories = list(category_fields.keys())
    if old_index < 0 or old_index >= len(categories):
        return  # Invalid old_index
    category = categories.pop(old_index)
    new_index = max(0, min(new_index, len(categories)))  # Ensure new_index is within bounds
    categories.insert(new_index, category)

    # Reorder category_fields based on the new category order
    ordered_fields = {category: category_fields[category] for category in categories}
    category_fields = ordered_fields

    # Save the updated category_fields to the JSON file
    save_category_fields_to_json(current_db, category_fields)

    # Refresh the UI
    update_ui()

def move_tab_left(tab_text):
    keys = list(category_fields.keys())
    index = keys.index(tab_text)
    if index > 0:
        keys[index], keys[index - 1] = keys[index - 1], keys[index]
        reorder_category_fields(keys)
        update_ui()
        save_category_fields_to_json(current_db, category_fields)

def move_tab_right(tab_text):
    keys = list(category_fields.keys())
    index = keys.index(tab_text)
    if index < len(keys) - 1:
        keys[index], keys[index + 1] = keys[index + 1], keys[index]
        reorder_category_fields(keys)
        update_ui()
        save_category_fields_to_json(current_db, category_fields)

def reorder_category_fields(new_order):
    global category_fields
    new_category_fields = {k: category_fields[k] for k in new_order}
    category_fields = new_category_fields

def update_tab_order_in_json(notebook):
    tab_order = [notebook.tab(tab, "text") for tab in notebook.tabs()]
    save_category_fields_to_json(current_db, category_fields, tab_order)
    refresh_gui()

def on_close():
    save_last_used_db()
    root.destroy()

load_last_used_db()
ensure_item_transactions_table_exists()

# Bind Ctrl + F to open the search window
root.bind('<Control-f>', lambda event: open_search_window())
# Bind keys to the functions
root.bind('<Control-Down>', lambda event: next_theme())
root.bind('<Control-Up>', lambda event: previous_theme())
root.bind('<Control-r>', lambda event: refresh_gui())
root.bind('<Control-w>', open_warning_level_settings)
root.bind('<Control-e>', open_graphic_menu)
root.bind('<Control-s>', open_shortcut_snitch)
root.bind('<Control-i>', open_about_window)
root.bind('<Control-k>', open_shortcut_keyboard)
root.bind('<Control-u>', configure_email_account)
notebook.bind("<Button-2>", lambda event: on_tab_right_click(event, notebook)) # UNIX
notebook.bind("<Button-3>", lambda event: on_tab_right_click(event, notebook)) # WINDOWS
root.bind('<Control-Shift-Right>', lambda event: select_next_database())
root.bind('<Control-Shift-Left>', lambda event: select_previous_database())
root.bind('<Control-Shift-C>', lambda event: create_db_shortcut())
root.bind('<Control-Shift-A>', lambda event: add_table_shortcut())
root.bind('<Control-Shift-BackSpace>', wipe_out_db)
root.bind('<Control-Shift-B>', backup_db)
root.bind('<Control-Shift-N>', start_as_new_db)

root.protocol("WM_DELETE_WINDOW", on_close)
# Run the application
root.mainloop()
