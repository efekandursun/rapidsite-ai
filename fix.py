import re

with open('core/whatsapp_handler.py', 'r') as f:
    content = f.read()

start_marker = "def format_confirmation(result: dict) -> str:"
end_marker = "def handle_incoming_message(msg_body: str, from_number: str) -> str:"

new_func = '''def format_confirmation(result: dict) -> str:
    """
    Format confirmation message for user based on Procore fields.
    """
    if 'direct_reply' in result:
        return result['direct_reply']

    parsed_list = result.get('parsed_data_list', [])
    report_ids = result.get('report_ids', [])
    
    if not parsed_list:
        return "[WARNING] Message received but could not be processed."
        
    completed_msgs = []
    
    for i, parsed in enumerate(parsed_list):
        r_id = report_ids[i] if i < len(report_ids) else 'N/A'
        
        log_type = parsed.get('log_type', 'unknown').lower()
        msg = f"[ID: #{r_id} | TYPE: {log_type.upper()}]\\n"
        
        def val(v): return str(v) if v not in (None, "", "null", "Boş", "Empty") else "There is no information"
        
        loc = parsed.get('location', {})
        loc_name = loc.get('name') if isinstance(loc, dict) else loc
        
        if log_type == "weather":
            w = parsed.get('weather_details', {})
            msg += f"- Time: {val(w.get('time_observed'))}\\n"
            msg += f"- Delay: {val(w.get('delay'))}\\n"
            msg += f"- Sky/Temp: {val(w.get('sky'))} / {val(w.get('temperature'))}\\n"
            msg += f"- Precipitation: {val(w.get('precipitation'))}\\n"
            
        elif log_type == "manpower":
            crew = parsed.get('crew', {})
            msg += f"- Company/Sub: {val(crew.get('company_name'))}\\n"
            msg += f"- Workers: {val(crew.get('count') or parsed.get('quantity'))}\\n"
            msg += f"- Hours: {val(crew.get('hours'))}\\n"
            msg += f"- Location: {val(loc_name)}\\n"
            
        elif log_type == "timecards":
            t = parsed.get('timecard_details', {})
            msg += f"- Employee: {val(t.get('employee'))}\\n"
            msg += f"- Cost Code: {val(parsed.get('cost_code'))}\\n"
            msg += f"- Type: {val(t.get('type'))}\\n"
            msg += f"- Hours: {val(t.get('hours'))}\\n"
            
        elif log_type == "equipment":
            details = parsed.get('equipment_details', {})
            msg += f"- Equipment Name: {val(parsed.get('item'))}\\n"
            msg += f"- Hours Operating: {val(details.get('hours_operating'))}\\n"
            idle_val = val(details.get('hours_idle'))
            msg += f"- Hours Idle: {idle_val if idle_val != 'There is no information' else '0'}\\n"
            
        elif log_type == "visitors":
            v = parsed.get('visitor_details', {})
            msg += f"- Visitor: {val(v.get('visitor'))}\\n"
            msg += f"- Time: {val(v.get('start'))} to {val(v.get('end'))}\\n"
            
        elif log_type == "phone_calls":
            c = parsed.get('call_details', {})
            msg += f"- From: {val(c.get('call_from'))}\\n"
            msg += f"- To: {val(c.get('call_to'))}\\n"
            
        elif log_type == "inspections":
            i_det = parsed.get('inspection_details', {})
            msg += f"- Type: {val(i_det.get('inspection_type'))}\\n"
            msg += f"- Inspector: {val(i_det.get('inspector_name'))}\\n"
            msg += f"- Area: {val(i_det.get('inspection_area'))}\\n"
            
        elif log_type == "delivery":
            details = parsed.get('delivery_details', {})
            msg += f"- Delivery From: {val(details.get('delivery_from'))}\\n"
            msg += f"- Contents: {val(details.get('contents'))}\\n"
            
        elif log_type == "safety":
            s = parsed.get('safety_details', {})
            msg += f"- Subject: {val(parsed.get('item'))}\\n"
            msg += f"- Notice: {val(s.get('safety_notice'))}\\n"
            msg += f"- Issued To: {val(s.get('issued_to'))}\\n"
            
        elif log_type == "accidents":
            a = parsed.get('accident_details', {})
            msg += f"- Party: {val(a.get('party_involved'))}\\n"
            msg += f"- Company: {val(a.get('company_involved'))}\\n"
            
        elif log_type == "productivity":
            pd = parsed.get('productivity_details', {})
            msg += f"- Company: {val(pd.get('company'))}\\n"
            msg += f"- Delivered: {val(pd.get('quantity_delivered'))}\\n"
            msg += f"- Put in Place: {val(pd.get('quantity_put_in_place'))}\\n"
            
        elif log_type == "dumpster":
            d = parsed.get('dumpster_details', {})
            msg += f"- Company: {val(d.get('company'))}\\n"
            msg += f"- Delivered: {val(d.get('delivered'))}\\n"
            msg += f"- Removed: {val(d.get('removed'))}\\n"
            
        elif log_type == "waste":
            w = parsed.get('waste_details', {})
            msg += f"- Material: {val(w.get('material'))}\\n"
            msg += f"- Disposed By: {val(w.get('disposed_by'))}\\n"
            msg += f"- Quantity: {val(w.get('approximate_quantity'))}\\n"
            
        elif log_type == "scheduled_work":
            sw = parsed.get('scheduled_work_details', {})
            msg += f"- Resource: {val(sw.get('resource'))}\\n"
            msg += f"- Workers: {val(sw.get('workers'))}\\n"
            msg += f"- Hours: {val(sw.get('hours'))}\\n"
            
        elif log_type == "delays":
            d = parsed.get('delay_details', {})
            msg += f"- Type: {val(d.get('delay_type'))}\\n"
            msg += f"- Duration (hrs): {val(d.get('duration_hours'))}\\n"
            
        else:
            msg += f"- Item: {val(parsed.get('item'))}\\n"
            msg += f"- Quantity: {val(parsed.get('quantity'))} {val(parsed.get('unit'))}\\n"
        
        # Common tail
        if log_type not in ("weather", "manpower", "timecards"):
            if loc_name:
                msg += f"- Location: {val(loc_name)}\\n"
                
        msg += f"- Comments: {val(parsed.get('description'))}"
        completed_msgs.append(msg)
            
    final_msg = ""
    if completed_msgs:
        final_msg += "*REPORT READY*\\n\\n" + "\\n\\n".join(completed_msgs)
        
    return final_msg

'''

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_func + content[end_idx:]
    with open('core/whatsapp_handler.py', 'w') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('COULD NOT FIND MARKERS')
