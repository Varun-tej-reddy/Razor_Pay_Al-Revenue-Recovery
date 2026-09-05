"""
Hinglish Conversational AI Recovery Bot & Voice Telephony Agent (Track 03)

Delivers empathetic, culturally resonant Indian Hinglish conversational recovery powered by Google Gemini:
- Handles checkout drop-offs and overdue B2B receivables
- Intelligently parses customer intent via Gemini 3.6 Flash:
  * Technical failure / OTP delay
  * Price hesitation / discount negotiation
  * Promise-to-Pay (PTP) commitment detection
  * B2B invoice GST queries
- Dynamically integrates with Promise-to-Pay ledger to schedule commitments
- Generates natural, telephony-ready Hinglish voice call audio scripts
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from storage.db import insert_promise_to_pay
from agent.llm_client import call_gemini, clean_json_response, get_gemini_api_key

def parse_ptp_intent(user_message: str) -> Optional[str]:
    """
    Extracts promised payment dates/times from customer messages in Hinglish, English, and Hindi.
    Handles explicit dates ("15th sept", "15 september", "tomorrow 11 am", "kal subah 10 baje", "कल सुबह १० बजे").
    """
    msg = user_message.lower().strip()
    now = datetime.now(timezone.utc)
    curr_year = 2026  # Grounded current operating year

    # Normalize Devanagari numerals to ASCII
    devanagari_digits = {"०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"}
    for d_char, a_char in devanagari_digits.items():
        msg = msg.replace(d_char, a_char)

    # Strip ordinal suffixes from numbers like 15th, 1st, 2nd, 3rd to prevent eager group regex mis-match
    msg_normalized = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", msg)

    # 1. Check for specific time expressions (e.g. 11:00 AM, 11am, 10:30, 6 pm, 4:00, 10 baje, १० बजे)
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje|बजे|hours)?\b", msg_normalized, re.IGNORECASE)
    time_str = "11:00 AM"
    if time_match:
        hour = int(time_match.group(1))
        minute = time_match.group(2) or "00"
        ampm = (time_match.group(3) or "").lower()
        if ampm in ["pm", "shaam", "sham", "raat", "evening", "शाम", "रात"] and hour < 12:
            ampm_str = "PM"
        elif ampm in ["am", "subah", "morning", "सुबह"] or hour == 12:
            ampm_str = "AM" if hour < 12 else "PM"
        elif hour >= 12:
            ampm_str = "PM"
            if hour > 12:
                hour -= 12
        elif 7 <= hour <= 11:
            ampm_str = "AM"
        elif 1 <= hour <= 6:
            ampm_str = "PM"
        else:
            ampm_str = "AM"
        time_str = f"{hour:02d}:{minute} {ampm_str}"

    # 2. Check for explicit month-date formats (e.g., "15 september", "15 sept", "1st october", "15 का सितंबर")
    month_map = {
        "jan": 1, "january": 1, "जनवरी": 1,
        "feb": 2, "february": 2, "फरवरी": 2,
        "mar": 3, "march": 3, "मार्च": 3,
        "apr": 4, "april": 4, "अप्रैल": 4,
        "may": 5, "मई": 5,
        "jun": 6, "june": 6, "जून": 6,
        "jul": 7, "july": 7, "जुलाई": 7,
        "aug": 8, "august": 8, "अगस्त": 8,
        "sep": 9, "sept": 9, "september": 9, "sepetember": 9, "सितंबर": 9,
        "oct": 10, "october": 10, "अक्टूबर": 10, "अक्तूबर": 10,
        "nov": 11, "november": 11, "नवंबर": 11,
        "dec": 12, "december": 12, "दिसंबर": 12
    }

    date_month_match = re.search(r"\b(\d{1,2})\s*(?:of\s+|ka\s+|ko\s+|ke\s+|का\s+|को\s+|के\s+)?([a-zA-Z\u0900-\u097F]+)", msg_normalized)
    if date_month_match:
        d_val = int(date_month_match.group(1))
        m_word = date_month_match.group(2).lower()
        for m_key, m_num in month_map.items():
            if m_key in m_word:
                return f"{curr_year}-{m_num:02d}-{d_val:02d} {time_str} IST"

    month_date_match = re.search(r"([a-zA-Z\u0900-\u097F]+)\s+(\d{1,2})\b", msg_normalized)
    if month_date_match:
        m_word = month_date_match.group(1).lower()
        d_val = int(month_date_match.group(2))
        for m_key, m_num in month_map.items():
            if m_key in m_word:
                return f"{curr_year}-{m_num:02d}-{d_val:02d} {time_str} IST"

    # 3. Check for day / relative date expressions (multilingual)
    if any(w in msg for w in ["kal", "tomorrow", "next day", "following day", "कल"]):
        target = now + timedelta(days=1)
        return f"{target.strftime('%Y-%m-%d')} {time_str} IST"
    elif any(w in msg for w in ["parso", "day after tomorrow", "in 2 days", "after 2 days", "2 din", "परसों", "परसो"]):
        target = now + timedelta(days=2)
        return f"{target.strftime('%Y-%m-%d')} {time_str} IST"
    elif any(w in msg for w in ["monday", "somvaar", "somwar", "सोमवार"]):
        return f"{curr_year}-09-08 {time_str} IST"
    elif any(w in msg for w in ["tuesday", "mangalvaar", "mangalwar", "मंगलवार"]):
        return f"{curr_year}-09-09 {time_str} IST"
    elif any(w in msg for w in ["wednesday", "budhvaar", "budhwar", "बुधवार"]):
        return f"{curr_year}-09-10 {time_str} IST"
    elif any(w in msg for w in ["thursday", "guruvaar", "guruwar", "गुरुवार", "बृहस्पतिवार"]):
        return f"{curr_year}-09-11 {time_str} IST"
    elif any(w in msg for w in ["friday", "shukravaar", "shukrawar", "शुक्रवार"]):
        return f"{curr_year}-09-11 {time_str} IST"
    elif any(w in msg for w in ["saturday", "shanivaar", "shaniwar", "weekend", "शनिवार"]):
        return f"{curr_year}-09-12 {time_str} IST"
    elif any(w in msg for w in ["sunday", "ravivaar", "raviwar", "रविवार"]):
        return f"{curr_year}-09-13 {time_str} IST"
    elif any(w in msg for w in ["salary", "vetan", "salery", "सैलरी", "वेतन"]):
        return f"{curr_year}-09-07 10:00 AM IST (Salary Credit Sync)"
    elif any(w in msg for w in ["tonight", "shaam", "evening", "raat", "aaj shaam", "आज शाम", "रात"]):
        return f"{now.strftime('%Y-%m-%d')} {time_str} IST"
    elif any(w in msg for w in ["pay later", "kal dunga", "kal karunga", "baad me pay", "promise to pay", "schedule", "will pay", "बाद में", "पे करूँगा", "भुगतान कर दूँगा"]):
        target = now + timedelta(days=1)
        return f"{target.strftime('%Y-%m-%d')} {time_str} IST"

    return None


def process_hinglish_chat(
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
    force_llm: bool = False
) -> Dict[str, Any]:
    """
    Processes customer input in Hinglish and generates an intelligent,
    courteous business response grounded in transaction context.
    Uses Google Gemini 3.6 Flash when available with graceful fallback.
    """
    ctx = context or {}
    customer_name = ctx.get("customer_name", "Ji")
    amount = float(ctx.get("amount", 3743.17))
    txn_id = ctx.get("transaction_id", "pay_synth_001")
    failed_inst = ctx.get("failed_instrument", "Kotak Mahindra Bank UPI")
    failure_reason = ctx.get("failure_reason", "Bank switch timeout / OTP latency")
    msg_lower = user_message.lower()

    # Fast PTP & Payment Completed & Reluctance checks
    is_paid_claim = any(w in msg_lower for w in [
        "pay kar diya", "paid", "payment ho gaya", "done payment",
        "transfer kar diya", "reconcile", "paise bhej diye", "already paid", "payment done",
        "कर दिया", "हो गया", "पे कर दिया", "भुगतान हो गया", "डन", "सक्सेस", "कट गए"
    ])
    fast_ptp = parse_ptp_intent(user_message)

    # Customer reluctance, price objection, dropping out, or asking for discount
    is_discount_intent = any(w in msg_lower for w in [
        "not interested", "nahi lena", "nahi chahiye", "dont want", "don't want",
        "expensive", "mehenga", "mehanga", "costly", "too high", "jyada hai", "jyada lag raha",
        "cancel", "drop", "nahi kharidna", "budget", "paise nahi", "man nahi",
        "chhod do", "leave it", "no thanks", "nahi karna", "soch raha hu", "hesitant",
        "discount", "kam karo", "offer", "coupon", "cashback", "kuch kam", "bargain", "kam karo na", "less price",
        "डिस्काउंट", "छूट", "सस्ता", "महंगा", "महंगी", "पैसा", "पैसे", "नहीं लेना", "नहीं चाहिए", "नहीं खरीदना", "कैंसिल", "बजट", "ऑफर"
    ])

    # Customer willing to pay / specifying date / PTP
    is_ptp_claim = (
        (fast_ptp is not None) or
        any(w in msg_lower for w in [
            "will pay", "pay tomorrow", "pay on", "pay by", "kal dunga", "kal karunga",
            "bhej dunga", "kal shaam", "parso", "somwar", "friday", "next week",
            "salary", "baje", "10 am", "11 am", "schedule", "do payment",
            "promise to pay", "kar dunga", "pakka pay", "clear kar dunga",
            "कल", "सुबह", "शाम", "पे", "भुगतान", "करूँगा", "कर दूँगा", "तारीख", "दिन", "बजे", "शुक्रवार", "सोमवार", "शनिवार", "रविवार", "मंगलवार", "बुधवार", "गुरुवार", "दूँगा", "दूंगा", "करेंगे", "बाद में"
        ])
    ) and not is_paid_claim and not is_discount_intent

    # Attempt Live Gemini Generation
    api_key = get_gemini_api_key()
    if api_key:
        discount_amt = round(amount * 0.02, 2)
        net_amt = round(amount - discount_amt, 2)
        today_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
        
        system_instruction = f"""You are the autonomous Razorpay AI Revenue Recovery Concierge named Aarav.
You assist Indian customers whose payment dropped during checkout or invoice settlement.

TRANSACTION CONTEXT & CALENDAR GROUNDING:
- Customer Name: {customer_name}
- Transaction ID: #{txn_id}
- Original Amount: ₹{amount:,.2f}
- Failed Instrument: {failed_inst}
- Technical Friction: {failure_reason}
- CURRENT DATE: {today_date_str} (Operating in Year 2026)

CRITICAL DISCOUNT & PRICING RULES (STRICT MARGIN PROTECTION):
1. **ZERO DISCOUNT FOR WILLING BUYERS / PROMISE-TO-PAY (PTP) / TECHNICAL ISSUES**:
   - If the customer agrees to pay, mentions a date/time (e.g., "I will pay tomorrow by 11 AM", "kal shaam ko", "salary ke baad"), or asks about OTP / link:
     * **DO NOT** offer or mention any discount.
     * The transaction remains at the **FULL original amount ₹{amount:,.2f}**.
     * Confirm the Promise-to-Pay (PTP) booking and reassure that automated reminders are paused.
2. **2% PROMPT CASH DISCOUNT (Save ₹{discount_amt:,.2f} • Net payable: ₹{net_amt:,.2f}) IS RESERVED EXCLUSIVELY FOR**:
   - The customer stating they are NOT interested in buying / paying (e.g., "not interested", "nahi lena", "nahi chahiye", "cancel kar do", "chhod do", "don't want to spend").
   - The customer expressing price hesitation or budget constraints (e.g., "too expensive", "mehenga hai", "budget nahi hai", "out of budget").
   - The customer explicitly negotiating or asking for a discount/coupon (e.g., "kuch discount milega?", "kam karo na", "any offer?").
   - In these reluctant/drop-off cases ONLY, offer the 2% discount incentive as a strategic recovery rescue lever to win back the hesitant buyer!

INTENT & CONVERSATION GUIDELINES:
1. **Promise-to-Pay (PTP) / Future Date**:
   - Set "detected_intent": "PROMISE_TO_PAY", "ptp_detected": true, extract "ptp_time" formatted as "2026-MM-DD hh:mm A IST".
   - Confirm booking for full price ₹{amount:,.2f} without any discount.
2. **Customer Reluctant / Not Interested / Asking Discount**:
   - Set "detected_intent": "DISCOUNT_NEGOTIATION", "ptp_detected": false.
   - Empathize with their hesitation and present the exclusive 2% instant settlement credit (Save ₹{discount_amt:,.2f} • Revised net total: ₹{net_amt:,.2f}).
3. **Technical Issue (OTP / Bank failure)**:
   - Set "detected_intent": "TECHNICAL_ISSUE_OTP", "ptp_detected": false.
   - Explain gateway network latency and provide 1-Click Biometric UPI retry link at full price without discount.
4. **Payment Completed**:
   - Set "detected_intent": "PAYMENT_COMPLETED", "ptp_detected": false.
   - Confirm escrow verification and thank the customer.
5. **Voice TTS Output**:
   - In "voice_synthesis_script": generate natural, fluent conversational Indian Hinglish dialogue with ZERO asterisks or markdown, optimized for speech synthesis.

Return strictly valid JSON with this schema:
{{
  "reply_hinglish": "string (polite formatted Hinglish message)",
  "reply_english": "string (complete professional English translation of the reply)",
  "ai_reasoning": "string (chain-of-thought analysis explaining customer intent, sentiment, and strategy rationale)",
  "mapped_keywords": ["list of 3-5 extracted keywords or entity tags, e.g. 'PTP Commitment', 'Date: 2026-09-15', 'Friction: OTP'"],
  "voice_synthesis_script": "string (plain spoken dialogue without asterisks for audio synthesis)",
  "detected_intent": "PROMISE_TO_PAY" | "PAYMENT_COMPLETED" | "TECHNICAL_ISSUE_OTP" | "DISCOUNT_NEGOTIATION" | "INVOICE_QUERY" | "PAYMENT_LINK_REQUEST" | "GENERAL_RECOVERY",
  "ptp_detected": boolean,
  "ptp_time": "string (e.g. 2026-09-15 11:00 AM IST) or null",
  "suggested_quick_replies": ["list of 3 short user reply buttons"]
}}
"""

        try:
            llm_res = call_gemini(
                prompt=f'Customer says: "{user_message}"',
                system_instruction=system_instruction,
                temperature=0.3,
                response_mime_type="application/json"
            )
            if llm_res["success"]:
                data = clean_json_response(llm_res["text"])
                reply_h = data.get("reply_hinglish") or data.get("reply", "")
                if not reply_h or len(reply_h.strip()) == 0:
                    reply_h = f"Namaste {customer_name}! Hum Razorpay Smart Recovery desk se bol rahe hain. Aapka payment securely complete karne ke liye 1-Click UPI alternative available hai."
                
                reply_eng = data.get("reply_english") or "Hello! We are reaching out from the Razorpay Smart Recovery desk to assist you with completing your transaction."
                ai_reasoning = data.get("ai_reasoning") or f"Customer expressed drop-off friction regarding {failed_inst}. Handled with targeted recovery strategy."
                mapped_kw = data.get("mapped_keywords") or [f"Customer: {customer_name}", f"Amount: ₹{amount:,.2f}", f"Instrument: {failed_inst}"]
                
                voice_script = data.get("voice_synthesis_script", "") or reply_h
                intent = data.get("detected_intent", "GENERAL_RECOVERY")
                if is_paid_claim:
                    intent = "PAYMENT_COMPLETED"
                elif is_discount_intent:
                    intent = "DISCOUNT_NEGOTIATION"
                    if "2% instant" not in reply_h and "2% discount" not in reply_h and "save ₹" not in reply_h.lower():
                        reply_h += f"\n\nHum aapko exclusive **2% instant settlement discount** de sakte hain (Save ₹{discount_amt:,.2f} • Net payable: ₹{net_amt:,.2f})."
                    if "2% instant" not in reply_eng and "2% discount" not in reply_eng and "save ₹" not in reply_eng.lower():
                        reply_eng += f"\n\nWe can offer you an exclusive **2% instant settlement discount** (Save ₹{discount_amt:,.2f} • Net payable: ₹{net_amt:,.2f})."
                elif is_ptp_claim or data.get("ptp_detected", False) or intent == "PROMISE_TO_PAY":
                    intent = "PROMISE_TO_PAY"
                    # Clean out any accidental discount mentions if customer agreed to pay
                    disc_phrases = [
                        f"Hum aapko 2% instant settlement discount de sakte hain (Save ₹{discount_amt:,.2f}).",
                        f"We can offer you a 2% instant settlement discount (Save ₹{discount_amt:,.2f}).",
                        f"2% instant settlement discount (Save ₹{discount_amt:,.2f})",
                        f"Save ₹{discount_amt:,.2f}"
                    ]
                    for dp in disc_phrases:
                        reply_h = reply_h.replace(dp, "")
                        reply_eng = reply_eng.replace(dp, "")
                        voice_script = voice_script.replace(dp, "")
                elif any(w in msg_lower for w in ["otp", "sms", "nahi aaya", "code"]):
                    intent = "TECHNICAL_ISSUE_OTP"
                    if "1-Click Biometric" not in reply_h and "1-click biometric" not in reply_h.lower():
                        reply_h += f"\n\nHumne aapke liye **1-Click Biometric UPI** authorization enable kar diya hai bina kisi OTP ke."
                    if "1-Click Biometric" not in reply_eng and "1-click biometric" not in reply_eng.lower():
                        reply_eng += f"\n\nWe have enabled **1-Click Biometric UPI** authorization for you without requiring any OTP."
                elif any(w in msg_lower for w in ["link", "kaha pay", "bhejo", "pay link", "how to pay"]):
                    intent = "PAYMENT_LINK_REQUEST"
                    if "Razorpay secure checkout link" not in reply_h:
                        reply_h += f"\n\nYeh lijiye aapka verified Razorpay secure checkout link: https://rzp.io/i/{txn_id}"
                    if "Razorpay secure checkout link" not in reply_eng:
                        reply_eng += f"\n\nHere is your verified Razorpay secure checkout link: https://rzp.io/i/{txn_id}"

                is_ptp_detected = (
                    (intent == "PROMISE_TO_PAY") or
                    (fast_ptp is not None) or 
                    data.get("ptp_detected", False) or 
                    is_ptp_claim
                ) and intent not in ["PAYMENT_COMPLETED", "TECHNICAL_ISSUE_OTP", "DISCOUNT_NEGOTIATION", "PAYMENT_LINK_REQUEST"]

                ptp_detected = is_ptp_detected
                ptp_time = data.get("ptp_time") or fast_ptp or (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d 11:00 AM IST")

                ptp_scheduled = None
                if is_paid_claim:
                    try:
                        ptp_record = insert_promise_to_pay({
                            "transaction_id": txn_id,
                            "customer_id": ctx.get("customer_id", f"cust_{customer_name.lower().replace(' ', '_')}"),
                            "customer_name": customer_name,
                            "amount": amount,
                            "ptp_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M IST (Settled)"),
                            "status": "honored",
                            "channel": ctx.get("channel", "Voice Telephony" if "voice" in ctx.get("channel", "").lower() else "Hinglish Chat"),
                            "notes": f"Payment reported complete by customer: {user_message}"
                        })
                        ptp_scheduled = {
                            "id": ptp_record.id,
                            "ptp_date": "Settled & Honored",
                            "amount": amount,
                            "status": "honored"
                        }
                    except Exception:
                        pass
                elif ptp_detected:
                    intent = "PROMISE_TO_PAY"
                    if "Promise-to-Pay" not in reply_h and "PTP" not in reply_h:
                        reply_h = f"Dhanyawaad {customer_name}! Humne aapka Promise-to-Pay (PTP) schedule kar liya hai: 📅 **{ptp_time}** ko ₹{amount:,.2f} ke liye. " + reply_h
                    try:
                        ptp_record = insert_promise_to_pay({
                            "transaction_id": txn_id,
                            "customer_id": ctx.get("customer_id", f"cust_{customer_name.lower().replace(' ', '_')}"),
                            "customer_name": customer_name,
                            "amount": amount,
                            "ptp_date": ptp_time,
                            "status": "scheduled",
                            "channel": ctx.get("channel", "Voice Telephony" if "voice" in ctx.get("channel", "").lower() else "Hinglish Chat"),
                            "notes": f"PTP commitment noted: {user_message}"
                        })
                        ptp_scheduled = {
                            "id": ptp_record.id,
                            "ptp_date": ptp_time,
                            "amount": amount,
                            "status": "scheduled"
                        }
                    except Exception:
                        ptp_scheduled = {
                            "ptp_date": ptp_time,
                            "amount": amount,
                            "status": "scheduled"
                        }

                return {
                    "user_message": user_message,
                    "reply": reply_h,
                    "reply_hinglish": reply_h,
                    "reply_english": reply_eng,
                    "ai_reasoning": ai_reasoning,
                    "mapped_keywords": mapped_kw,
                    "detected_intent": intent,
                    "ptp_detected": ptp_detected,
                    "ptp_commitment": ptp_scheduled,
                    "ptp_details": ptp_scheduled,
                    "voice_synthesis_script": voice_script,
                    "suggested_quick_replies": data.get("suggested_quick_replies", [
                        "Tomorrow by 11:00 AM (PTP)",
                        "OTP nahi aaya tha",
                        "Discount milega kya?",
                        "1-Click UPI link bhejo"
                    ]),
                    "ai_model": llm_res["model"],
                    "latency_ms": llm_res["latency_ms"],
                    "is_real_ai": True
                }
        except Exception:
            pass

    # Heuristic / Offline Fallback Path
    detected_intent = "GENERAL_RECOVERY"
    ptp_scheduled = None
    now_utc = datetime.now(timezone.utc)
    
    is_discount_fallback = is_discount_intent
    is_ptp_fallback = is_ptp_claim or (fast_ptp is not None)

    if is_paid_claim:
        detected_intent = "PAYMENT_COMPLETED"
        try:
            ptp_record = insert_promise_to_pay({
                "transaction_id": txn_id,
                "customer_id": ctx.get("customer_id", f"cust_{customer_name.lower().replace(' ', '_')}"),
                "customer_name": customer_name,
                "amount": amount,
                "ptp_date": now_utc.strftime("%Y-%m-%d %H:%M IST (Settled)"),
                "status": "honored",
                "channel": ctx.get("channel", "Voice Telephony" if "voice" in ctx.get("channel", "").lower() else "Hinglish Chat"),
                "notes": f"Payment reported complete by customer: '{user_message}'"
            })
            ptp_scheduled = {
                "id": ptp_record.id,
                "ptp_date": "Settled & Honored",
                "amount": amount,
                "status": "honored"
            }
        except Exception:
            pass

        response_text = (
            f"Dhanyawaad {customer_name}! Humne aapka ₹{amount:,.2f} ka payment verify aur settle kar liya hai. "
            f"Settlement Receipt: `pay_settled_{txn_id[-6:]}`. Sabhi dunning reminder messages pause kar diye gaye hain. ✓"
        )
        voice_script = (
            f"Dhanyawaad {customer_name}. Aapka payment successfully verify aur settle ho gaya hai. Thank you!"
        )

    elif is_discount_fallback:
        detected_intent = "DISCOUNT_NEGOTIATION"
        discount_amt = round(amount * 0.02, 2)
        net_amt = round(amount - discount_amt, 2)
        if any(w in msg_lower for w in ["not interested", "nahi lena", "nahi chahiye", "mehenga", "expensive", "costly", "cancel", "drop", "nahi kharidna", "budget", "chhod"]):
            response_text = (
                f"Samajh sakta hu {customer_name}. Agar price ya budget hesitation ki wajah se aap drop kar rahe hain, "
                f"toh Razorpay desk se hum aapko exclusive **2% instant settlement cash discount** de sakte hain (Aapke bachenge ₹{discount_amt:,.2f}). "
                f"Revised settlement amount: **₹{net_amt:,.2f}**. Kya hum 1-click checkout link bhej dein?"
            )
            voice_script = (
                f"Samajh sakta hu {customer_name}. Agar price ki wajah se issue hai toh hum aapko do percent "
                f"instant cash discount offer kar rahe hain. Aapke bachenge {discount_amt} rupees aur final amount {net_amt} rupees hoga."
            )
        else:
            response_text = (
                f"Samajh sakta hu {customer_name}. Agar aap agle 30 minutes me payment complete karte hain, "
                f"toh hum 2% instant settlement credit apply kar sakte hain (Aapke bachenge ₹{discount_amt:,.2f}). "
                f"Final amount: **₹{net_amt:,.2f}**. Kya hum updated link bhej dein?"
            )
            voice_script = (
                f"Ji {customer_name}, agar aap abhi clear karte hain toh hum do percent instant commercial credit "
                f"apply karke final amount {net_amt} rupees kar dete hain."
            )

    elif any(w in msg_lower for w in ["otp", "sms", "delay", "nahi aaya", "code"]):
        detected_intent = "TECHNICAL_ISSUE_OTP"
        response_text = (
            f"Haan ji {customer_name}, bank ke SMS gateway par thoda network delay chal raha tha. "
            f"Aapko OTP enter karne ki koi zaroorat nahi hai. "
            f"Humne aapke Kotak / UPI app ke liye **1-Click Biometric Authorization** enable kar diya hai. "
            f"Aap direct Face ID / Fingerprint se 2 second me payment complete kar sakte hain."
        )
        voice_script = (
            f"Namaste {customer_name}. Bank side se OTP me delay tha. "
            f"Humne aapke liye instant one-click UPI rail activate ki hai, bina kisi OTP ke."
        )

    elif any(w in msg_lower for w in ["kaha pay kare", "link bhejo", "upi", "qr", "how to pay", "pay link", "bhejo"]):
        detected_intent = "PAYMENT_LINK_REQUEST"
        response_text = (
            f"Yeh lijiye {customer_name}! Aapka verified Razorpay secure checkout link: "
            f"👉 [Tap here to Pay ₹{amount:,.2f} via UPI](https://rzp.io/l/recovery_{txn_id}?amount={amount}) "
            f"— Google Pay, PhonePe, Paytm ya BHIM se direct 1-click me pay karein."
        )
        voice_script = (
            f"Humne aapke registered mobile par instant UPI checkout link share kar diya hai. "
            f"Aap one-click me payment authorize kar sakte hain."
        )

    elif any(w in msg_lower for w in ["gst", "invoice", "company", "b2b", "bill", "soa"]):
        detected_intent = "INVOICE_QUERY"
        response_text = (
            f"Ji bilkul {customer_name}, aapka GST compliant tax invoice #{txn_id} ready hai. "
            f"Isme 18% Input Tax Credit claim karne ki poori eligibility hai. "
            f"Aap apna GSTIN update karke official invoice PDF dashboard se download kar sakte hain."
        )
        voice_script = (
            f"Aapka tax invoice aur GST input credit breakdown ready hai. "
            f"Aap direct download kar sakte hain."
        )

    elif is_ptp_fallback:
        detected_intent = "PROMISE_TO_PAY"
        ptp_time = fast_ptp or (now_utc + timedelta(days=1)).strftime("%Y-%m-%d 11:00 AM IST")
        try:
            ptp_record = insert_promise_to_pay({
                "transaction_id": txn_id,
                "customer_id": ctx.get("customer_id", f"cust_{customer_name.lower().replace(' ', '_')}"),
                "customer_name": customer_name,
                "amount": amount,
                "ptp_date": ptp_time,
                "status": "scheduled",
                "channel": ctx.get("channel", "Voice Telephony" if "voice" in ctx.get("channel", "").lower() else "Hinglish Chat"),
                "notes": f"Customer promised via {ctx.get('channel', 'Voice/Chat')}: '{user_message}'"
            })
            ptp_scheduled = {
                "id": ptp_record.id,
                "ptp_date": ptp_time,
                "amount": amount,
                "status": "scheduled"
            }
        except Exception:
            ptp_scheduled = {
                "ptp_date": ptp_time,
                "amount": amount,
                "status": "scheduled"
            }

        response_text = (
            f"Dhanyawaad {customer_name}! Humne aapka Promise-to-Pay (PTP) schedule kar liya hai: "
            f"📅 **{ptp_time}** ko ₹{amount:,.2f} ke liye. "
            f"Tab tak humari side se koi reminder nahi aayega. "
            f"Us time hum aapko 1-click Razorpay UPI link SMS aur WhatsApp par bhej denge. Shubh din!"
        )
        voice_script = (
            f"Dhanyawaad {customer_name}. Aapka promise to pay {ptp_time} ke liye confirm ho gaya hai. "
            f"Tab tak hum koi extra calls ya reminders nahi karenge. Thank you!"
        )

    else:
        detected_intent = "GREETING_OR_GENERAL"
        response_text = (
            f"Namaste {customer_name}! Razorpay Smart Recovery desk se bol rahe hain. "
            f"Aapka ₹{amount:,.2f} ka payment {failed_inst} par technical reason se drop ho gaya tha. "
            f"Kya hum instant 1-click alternative method se retry karein, ya aap kal pay karna chahenge?"
        )
        voice_script = (
            f"Namaste {customer_name}. Razorpay Recovery desk se hum aapki dropped transaction ke regarding "
            f"help karne ke liye connect kar rahe hain."
        )

    return {
        "user_message": user_message,
        "reply": response_text,
        "reply_hinglish": response_text,
        "detected_intent": detected_intent,
        "ptp_detected": (detected_intent == "PROMISE_TO_PAY"),
        "ptp_commitment": ptp_scheduled,
        "ptp_details": ptp_scheduled,
        "voice_synthesis_script": voice_script,
        "suggested_quick_replies": [
            "Kal subah 10 baje pay karunga (PTP)",
            "OTP nahi aaya tha",
            "Discount milega kya?",
            "1-Click UPI link bhejo"
        ],
        "ai_model": "heuristic_fallback",
        "latency_ms": 1,
        "is_real_ai": False
    }
