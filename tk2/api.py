import frappe
@frappe.whitelist()
def search_customer(email=None, mobile=None):
    """
    Search for an existing Customer by email or mobile.
    Returns the first matching Customer name if found, else None.
    """
    # 1. Search by email
    if email:
        found_by_email = frappe.get_all(
            "Customer", 
            filters={"email_id": email}, 
            fields=["name"]
        )
        if found_by_email:
            return found_by_email[0].name

    # 2. If no match or email wasn't provided, try mobile
    if mobile:
        found_by_mobile = frappe.get_all(
            "Customer",
            filters={"mobile_no": mobile},
            fields=["name"]
        )
        if found_by_mobile:
            return found_by_mobile[0].name

    # 3. None found
    return None
    
@frappe.whitelist()
def create_customer(customer_name, country=None, default_account=None, billing_currency=None, email=None, mobile=None):
    """
    Create a new Customer with defaults:
      - customer_group = "Individual"
      - Territory defaults to "Nigeria"
      
    If the customer's country is "Ghana", then:
      - Set territory to "Ghana"
      - Append a child row in the accounts table with the default receivable account
      - Set billing_currency from the provided billing_currency parameter
      
    Returns the newly created Customer name.
    """
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_group": "Individual",
        "territory": "Nigeria",   # default territory
        "country": country,
        "default_currency": billing_currency,
        "email_id": email,
        "mobile_no": mobile,
    })
    
    if customer.get("country") == "Ghana":
        customer.territory = "Ghana"
        # Append the default receivable account to the child table "accounts"
        if default_account:
            customer.append("accounts", {
                "account": default_account,
                "company": company
            })

    customer.insert(ignore_permissions=True)
    return customer.name






import frappe
from frappe.utils import nowdate
@frappe.whitelist()
def create_sales_invoice(customer_service_sheet):
    doc = frappe.get_doc("Customer Service Sheet", customer_service_sheet)

    if not doc.erp_customer:
        frappe.throw("No linked Customer found in erp_customer field")

    default_company = "Timmie Kettle"
    
    # Collect items from the Customer Service Sheet
    child_items = doc.get("item") or []
    sum_of_item_lines = 0.0
    for row in child_items:
        sum_of_item_lines += (row.qty * row.rate)

    # Determine first item code (if any)
    first_item_code = child_items[0].item_code.lower() if child_items else ""

    # ------------------------------------------------------------
    # 1) Compare sum_of_item_lines to doc.price, handle mismatch
    # ------------------------------------------------------------
    difference = sum_of_item_lines - doc.price

    # SCENARIO A: Invoice total is LESS than doc.price
    # -----------------------------------------------
    if difference < 0:
        # If first item is "comboex", skip throwing the error.
        # The invoice remains below doc.price, meaning the user
        # intentionally didn't charge the full price for combos.
        # If not Comboex, raise mismatch.
        if first_item_code != "comboex":
            frappe.throw(
                "Order Price is not equal to the invoice price. "
                "Please add comboex  on the first row if this is a combo."
            )

    # SCENARIO B: Invoice total is GREATER than doc.price
    # ---------------------------------------------------
    elif difference > 0:
        # Only allow discount if the first item is "comboex"
        if first_item_code != "comboex":
            frappe.throw(
                "Order Price is not equal to the invoice price, and the first row is not Comboex. "
                "Please add a comboex  on the first row or fix your items."
            )
        # If first item is comboex, we treat the difference as a discount
        # so that grand total = doc.price
        # (handled later after we create the Sales Invoice doc)

    # If difference == 0, they match perfectly → no action needed.

    # ------------------------------------------------------------
    # 2) Create the Sales Invoice
    # ------------------------------------------------------------
    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "company": default_company,
        "customer": doc.erp_customer,
        "posting_date": nowdate(),
        "set_posting_time": 1,
        "custom_agent": doc.custom_agent,
        "write_off_amount": 0.0,
        "base_write_off_amount": 0.0,
        "items": []
    })

    # Add items from the CSS child table to the Sales Invoice
    for row in child_items:
        si.append("items", {
            "item_code": row.item_code,
            "qty": row.qty,
            "rate": row.rate
        })

    # ------------------------------------------------------------
    # 3) If sum_of_item_lines > doc.price and first item is comboex,
    #    reduce invoice total via Additional Discount
    # ------------------------------------------------------------
    if difference > 0 and first_item_code == "comboex":
        si.apply_discount_on = "Grand Total"
        si.discount_amount = difference  # difference is (invoice_total - doc.price)
        si.additional_discount_percentage = 0

    # ------------------------------------------------------------
    # 4) Insert & Submit the Sales Invoice
    # ------------------------------------------------------------
    si.insert(ignore_permissions=True)
    si.submit()

    return si.name


import frappe
from frappe.utils import nowdate
import frappe

@frappe.whitelist()
def get_user_total_css():
    return frappe.db.count("Customer Service Sheet", filters={"cs": frappe.session.user})


@frappe.whitelist()
def get_user_delivered_css():
    return frappe.db.count("Customer Service Sheet", 
        filters={
            "cs": frappe.session.user,
            "status": "Delivered"
        }
    )

@frappe.whitelist()
def get_user_processing_css():
    return frappe.db.count("Customer Service Sheet",
        filters={
            "cs": frappe.session.user,
            "status": "Processing"
        }
    )

@frappe.whitelist()
def get_user_cancelled_css():

    return frappe.db.count("Customer Service Sheet",
        filters={
            "cs": frappe.session.user,
            "status": "Cancelled"
        }
    )




import frappe

@frappe.whitelist()
def get_css_by_digital_marketer_chart_data():
    """
    Returns chart data for Customer Service Sheets for the logged-in user,
    grouped by the 'digital_marketer' field.
    """
    user = frappe.session.user

    # Query Customer Service Sheet records for this user, grouped by digital_marketer.
    results = frappe.db.sql("""
        SELECT 
            digital_marketer, 
            COUNT(name) AS count
        FROM 
            `tabCustomer Service Sheet`
        WHERE 
            cs = %s
        GROUP BY 
            digital_marketer
        ORDER BY 
            digital_marketer
    """, (user,), as_dict=1)

    labels = []
    values = []
    for row in results:
        marketer = row.digital_marketer if row.digital_marketer else "Not Set"
        labels.append(marketer)
        values.append(row.count)

    chart_data = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": "Customer Service Sheets",
                    "values": values
                }
            ]
        },
        "type": "bar"
    }

    return chart_data


import frappe
from frappe import _
@frappe.whitelist()
def get_item_warehouse_stock(items, state=None):
    items = frappe.parse_json(items)
    stock_info = {}
    
    for item in items:
        query = """
            SELECT 
                sle.warehouse,
                wh.state,
                SUM(sle.actual_qty) as qty
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabWarehouse` wh ON sle.warehouse = wh.name
            WHERE sle.item_code = %s
        """
        params = [item]
        
        if state:
            query += " AND wh.state = %s"
            params.append(state)
        
        query += " GROUP BY sle.warehouse HAVING qty > 0"
        
        stock_info[item] = frappe.db.sql(query, params, as_dict=True)
    
    return stock_info


import frappe

@frappe.whitelist()  # make the method callable via HTTP
def get_agent_delivery_rate():
    """Return the global delivery % for the currently logged-in user (cs)."""
    user = frappe.session.user  # currently logged in user
    # If cs is an actual User doctype link, this might be enough
    # If you store user as Employee or some other link, adjust accordingly

    row = frappe.db.sql(
        """
        SELECT
            IFNULL(
                ROUND(
                    100 * SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN status <> 'Duplicate' THEN 1 ELSE 0 END), 0),
                2),
            0) AS delivery_percent
        FROM `tabCustomer Service Sheet`
        WHERE cs = %s
          AND docstatus < 2
        """,
        (user,),
        as_dict=True
    )

    delivery_rate = row[0].delivery_percent if row else 0.0

    # The returned dict keys can be:
    #  - value: actual numeric value to display
    #  - fieldtype (optional): to override display format
    #  - label (optional): to override label in the card
    return {
        "value": delivery_rate,
        "label": "Global Delivery %"
    }


import frappe
from frappe.utils import nowdate, get_first_day

@frappe.whitelist()
def get_agent_delivery_rate_mtd():
    """Return the month-to-date delivery % for the currently logged-in user."""
    user = frappe.session.user
    
    # Get the first day of the current month, e.g. "2025-02-01" if today's "2025-02-16"
    from_date = get_first_day(nowdate())  # e.g. "YYYY-MM-01"
    to_date = nowdate()                  # e.g. "YYYY-MM-DD" for today

    row = frappe.db.sql(
        """
        SELECT
            IFNULL(
                ROUND(
                    100 * SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN status <> 'Duplicate' THEN 1 ELSE 0 END), 0),
                2),
            0
            ) AS delivery_percent
        FROM `tabCustomer Service Sheet`
        WHERE cs = %s
          AND docstatus < 2
          AND creation BETWEEN %s AND %s
        """,
        (user, from_date, to_date),
        as_dict=True
    )

    delivery_rate = row[0].delivery_percent if row else 0.0
    return {
        "value": delivery_rate,
        "label": "MTD Delivery %"  # displayed on the card
    }

import frappe
from frappe import _

@frappe.whitelist()
def get_report(start_date, end_date, warehouse):
    """
    Returns an HTML formatted report of:
      1. Items sold (with qty) between start_date and end_date for the given warehouse.
      2. Current stock in the warehouse (only items with qty > 0).
    """
    # 1. Validate Inputs
    if not (start_date and end_date and warehouse):
        frappe.throw(_("Please provide Start Date, End Date, and Warehouse."))

    # 2. Query Sold Items
    # Adjust table names/fields if your setup differs
    sold_items = frappe.db.sql(
        """
        SELECT
            sii.item_code,
            SUM(sii.qty) AS sold_qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.posting_date BETWEEN %s AND %s
          AND sii.warehouse = %s
          AND si.docstatus = 1
        GROUP BY sii.item_code
        """,
        (start_date, end_date, warehouse),
        as_dict=True
    )

    # 3. Query Current Stock (from Bin)
    stock_items = frappe.db.sql(
        """
        SELECT item_code, actual_qty
        FROM `tabBin`
        WHERE warehouse = %s
          AND actual_qty > 0
        """,
        (warehouse,),
        as_dict=True
    )

    # 4. Build the HTML using Bootstrap
    #    - Two cards: one for "Items Sold", one for "Current Stock"
    #    - Tables styled with Bootstrap classes (table, table-bordered, table-striped)
    html = f"""
<div class="card mb-4">
  <div class="card-header">
    Items Sold from {start_date} to {end_date} in Warehouse: {warehouse}
  </div>
  <div class="card-body">
    <table class="table table-bordered table-striped">
      <thead>
        <tr>
          <th>Item Code</th>
          <th>Sold Quantity</th>
        </tr>
      </thead>
      <tbody>
"""

    if sold_items:
        for row in sold_items:
            html += f"""
        <tr>
          <td>{row.item_code}</td>
          <td>{row.sold_qty}</td>
        </tr>
"""
    else:
        html += """
        <tr>
          <td colspan="2">No items sold in this period.</td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>
</div>
"""

    # Second card for current stock
    html += f"""
<div class="card">
  <div class="card-header">
    Current Stock in Warehouse: {warehouse}
  </div>
  <div class="card-body">
    <table class="table table-bordered table-striped">
      <thead>
        <tr>
          <th>Item Code</th>
          <th>On Hand Quantity</th>
        </tr>
      </thead>
      <tbody>
"""

    if stock_items:
        for row in stock_items:
            html += f"""
        <tr>
          <td>{row.item_code}</td>
          <td>{row.actual_qty}</td>
        </tr>
"""
    else:
        html += """
        <tr>
          <td colspan="2">No items in stock.</td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>
</div>
"""

    # 5. Return the HTML string
    return html

import frappe

@frappe.whitelist()
def get_customer_service_users():
    # Store the current user
    current_user = frappe.session.user
    # Switch to Administrator
    frappe.set_user("Administrator")
    try:
        result = frappe.db.get_all(
            "User",
            filters={"role_profile_name": "Customer Service"},
            fields=["full_name", "email", "role_profile_name"]
        )
    finally:
        # Revert to the original user
        frappe.set_user(current_user)
    return result

@frappe.whitelist()
def update_user_role(user, active):
    new_role = "Customer Service" if active in [True, "1", 1] else "Test"
    current_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        frappe.db.set_value("User", user, "role_profile_name", new_role)
    finally:
        frappe.set_user(current_user)
    return True




import frappe

@frappe.whitelist()
def get_exchange_rate(currency, date):
    """Get exchange rate from `currency` to 'NGN' based on the Currency Exchange doctype."""
    # If it's the same currency, rate is 1
    if currency == "NGN":
        return 1.0

    # Attempt to fetch the latest rate on or before the given date
    rate = frappe.db.get_value(
        "Currency Exchange",
        filters={
            "from_currency": currency,
            "to_currency": "NGN",
            "date": ("<=", date)
        },
        fieldname="exchange_rate",
        order_by="date desc"
    )

    if not rate:
        frappe.throw(f"Exchange rate not found for {currency} to NGN on or before {date}")

    return rate


@frappe.whitelist()
def create_journal_entry(docname):
    """
    Creates and submits a Journal Entry for the given AD Spend document.
    """
    ad_spend = frappe.get_doc("AD Spend", docname)
    # Create a new Journal Entry document
    je = frappe.new_doc("Journal Entry")
    je.posting_date = ad_spend.date
    je.company = "Timmie Kettle"
    je.remark = f"Advert spend by {ad_spend.digital_marketer}"

    # Debit entry: Advertisement - TK account
    je.append("accounts", {
        "account": "Advertisement - TK",
        "debit_in_account_currency": ad_spend.amount_in_ngn,
        "credit_in_account_currency": 0,
    })

    # Credit entry: account specified in source_of_funds
    je.append("accounts", {
        "account": ad_spend.source_of_funds,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": ad_spend.amount_in_ngn,
    })

    je.insert(ignore_permissions=True)
    je.submit()
    return je.name



# In your custom app's Python file, e.g., agent_payments.py

import frappe
import json

@frappe.whitelist()
def create_journal_entry2(agent_payment, selected_invoices):
    # Parse JSON strings if necessary
    if isinstance(agent_payment, str):
        agent_payment = json.loads(agent_payment)
    if isinstance(selected_invoices, str):
        selected_invoices = json.loads(selected_invoices)
    
    # Calculate the sum of outstanding amounts from selected invoices
    invoice_total = sum([float(inv.get("outstanding_amount", 0)) for inv in selected_invoices])
    
    # Retrieve commission and charges (deductions)
    commission = float(agent_payment.get("commissions_deducted") or 0)
    charges = float(agent_payment.get("charges_deducted") or 0)
    
    # Compute the net payment: invoice_total minus the deductions
    computed_total = invoice_total - commission - charges
    
    # Validate that computed_total equals the Selected Total field
    selected_total_field = float(agent_payment.get("selected_total") or 0)
    if computed_total != selected_total_field:
        frappe.throw("The computed net payment (" + str(computed_total) +
                     ") does not equal the Selected Total (" + str(selected_total_field) + ").")
    
    # Create a new Journal Entry
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = agent_payment.get("date") or frappe.utils.nowdate()
    je.reference_no = agent_payment.get("name")
    je.reference_date = agent_payment.get("date") or frappe.utils.nowdate()
    
    # Retrieve company from the bank account (assuming bank links to an Account)
    company = frappe.db.get_value("Account", agent_payment.get("bank"), "company")
    je.company = company
    
    # Fetch the cost center
    cost_center = frappe.db.get_default("cost_center")
    
    # --- Journal Entry Lines ---
    # Debit: Bank with the net payment (selected_total)
    je.append("accounts", {
        "account": agent_payment.get("bank"),
        "debit_in_account_currency": computed_total,
        "credit_in_account_currency": 0,
        "party_type": "",
        "party": "",
        "cost_center": cost_center
    })
    
    # Credit: For each selected Sales Invoice, credit AR with the outstanding amount
    default_ar = frappe.get_cached_value("Company", company, "default_receivable_account")
    for inv in selected_invoices:
        amt = float(inv.get("outstanding_amount", 0))
        je.append("accounts", {
            "account": default_ar,
            "credit_in_account_currency": amt,
            "debit_in_account_currency": 0,
            "party_type": "Customer",
            "party": inv.get("customer"),
            "cost_center": cost_center,
            "reference_type": "Sales Invoice",
            "reference_name": inv.get("name")
        })
    
    # Debit: Commission on Sales – TK for the commission deducted (if any)
    if commission:
        je.append("accounts", {
            "account": "Commission on Sales - TK",
            "debit_in_account_currency": commission,
            "credit_in_account_currency": 0,
            "cost_center": cost_center
        })
    
    # Debit: Delivery Charges – TK for the charges deducted (if any)
    if charges:
        je.append("accounts", {
            "account": "Delivery Charges - TK",
            "debit_in_account_currency": charges,
            "credit_in_account_currency": 0,
            "cost_center": cost_center
        })
    
    je.insert()
    je.submit()
    
    return je.name





# In your custom app's Python file, e.g., agent_payments.py

import frappe

@frappe.whitelist()
def get_unpaid_invoices(agent):
    # Query Sales Invoices where custom_agent equals the provided agent and there is an outstanding amount.
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "custom_agent": agent,
            "outstanding_amount": [">", 0],
            "docstatus": 1          
        },
        fields=["posting_date", "name", "customer", "grand_total", "outstanding_amount"]
    )
    return invoices




import frappe
from datetime import date
import calendar
@frappe.whitelist()
def get_user_total_css_this_month():
    today = date.today()
    # First day of current month
    start_of_month = today.replace(day=1)
    # Last day of current month
    end_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    
    return frappe.db.count(
        "Customer Service Sheet",
        filters={
            "cs": frappe.session.user,
            "order_date": ["between", [start_of_month, end_of_month]]
        }
    )




