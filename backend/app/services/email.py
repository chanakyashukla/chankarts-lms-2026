"""
Email service abstraction for ChankArts Music Academy.
Provider-secure: credentials in environment variables, never exposed in frontend.
Supports Web3Forms for admin notifications and test mode for development.
"""
import os
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service abstraction using Web3Forms for admin notifications.
    Supports test mode for development without real email delivery.
    """
    
    def __init__(self):
        self.web3forms_access_key = os.getenv("WEB3FORMS_ACCESS_KEY", "")
        self.admin_email = os.getenv("ADMIN_EMAIL", "chankarts.official@gmail.com")
        self.from_name = os.getenv("FROM_NAME", "ChankArts Music Academy")
        self.test_mode = os.getenv("EMAIL_TEST_MODE", "true").lower() == "true"
        
        # Store test emails for verification
        self._test_emails: list[Dict[str, Any]] = []
    
    def _send_web3forms(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send email via Web3Forms or log in test mode."""
        
        # Test mode: log email instead of sending
        if self.test_mode:
            email_record = {
                "to": to_email,
                "subject": subject,
                "text_body": text_body,
                "html_body": html_body,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._test_emails.append(email_record)
            logger.info(f"[TEST MODE] Email captured: To={to_email}, Subject={subject}")
            return True
        
        # Production mode: send via Web3Forms
        if not self.web3forms_access_key:
            logger.warning("Web3Forms access key not configured. Email not sent.")
            return False
        
        try:
            payload = {
                "access_key": self.web3forms_access_key,
                "to": to_email,
                "from_name": self.from_name,
                "subject": subject,
                "html": html_body,
                "text": text_body or "",
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.web3forms.com/submit",
                    json=payload,
                )
                response.raise_for_status()
                
                result = response.json()
                if result.get("success"):
                    logger.info(f"Email sent to {to_email}: {subject}")
                    return True
                else:
                    logger.error(f"Web3Forms error: {result.get('message', 'Unknown error')}")
                    return False
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def get_test_emails(self) -> list[Dict[str, Any]]:
        """Return all emails captured in test mode."""
        return self._test_emails
    
    def clear_test_emails(self):
        """Clear captured test emails."""
        self._test_emails.clear()
    
    def send_registration_admin_notification(
        self,
        request_id: str,
        full_name: str,
        email: str,
        mobile: str,
        date_of_birth: str,
        is_minor: bool,
        address: str,
        guardian_name: str,
        guardian_relationship: str,
        guardian_email: str,
        guardian_mobile: str,
        selected_programmes: list,
        submitted_at: str,
        review_deadline: str,
    ) -> bool:
        """Send complete registration notification to admin via Web3Forms."""
        
        programmes_html = "".join(
            f"<li style='padding: 4px 0;'>{p.get('name', p.get('id', 'Unknown'))}</li>"
            for p in selected_programmes
        )
        programmes_text = "\n".join(
            f"  • {p.get('name', p.get('id', 'Unknown'))}"
            for p in selected_programmes
        )
        
        guardian_section_html = ""
        guardian_section_text = ""
        if is_minor and guardian_name:
            guardian_section_html = f"""
            <div style="margin-top: 24px;">
                <h3 style="color: #c9a96e; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Guardian Information</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; color: #666; width: 140px;">Name</td><td style="padding: 8px 0;">{guardian_name}</td></tr>
                    <tr><td style="padding: 8px 0; color: #666;">Relationship</td><td style="padding: 8px 0;">{guardian_relationship}</td></tr>
                    <tr><td style="padding: 8px 0; color: #666;">Mobile</td><td style="padding: 8px 0;">{guardian_mobile}</td></tr>
                    {"<tr><td style='padding: 8px 0; color: #666;'>Email</td><td style='padding: 8px 0;'>" + guardian_email + "</td></tr>" if guardian_email else ""}
                </table>
            </div>
            """
            guardian_section_text = f"""
GUARDIAN INFORMATION
--------------------
Name: {guardian_name}
Relationship: {guardian_relationship}
Mobile: {guardian_mobile}
{f"Email: {guardian_email}" if guardian_email else ""}
"""
        
        html_body = f"""
        <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0f17; color: #f5f5f5; border-radius: 12px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 32px; text-align: center; border-bottom: 2px solid #c9a96e;">
                <h1 style="color: #c9a96e; font-size: 20px; margin: 0 0 8px 0; letter-spacing: 0.1em;">CHANKARTS MUSIC ACADEMY</h1>
                <p style="color: #b8b8b8; font-size: 13px; margin: 0; font-style: italic;">Learn. Create. Perform.</p>
            </div>
            
            <div style="padding: 32px;">
                <div style="background: rgba(201, 169, 110, 0.1); border: 1px solid rgba(201, 169, 110, 0.2); border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                    <h2 style="color: #c9a96e; font-size: 16px; margin: 0 0 8px 0;">NEW REGISTRATION APPLICATION</h2>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Request ID:</strong> {request_id}</p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Submitted:</strong> {submitted_at}</p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Review Deadline:</strong> {review_deadline}</p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Status:</strong> <span style="color: #fbbf24;">Pending Approval</span></p>
                </div>
                
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #c9a96e; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Student Information</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="padding: 8px 0; color: #666; width: 140px;">Name</td><td style="padding: 8px 0;">{full_name}</td></tr>
                        <tr><td style="padding: 8px 0; color: #666;">Email</td><td style="padding: 8px 0;">{email}</td></tr>
                        <tr><td style="padding: 8px 0; color: #666;">Mobile</td><td style="padding: 8px 0;">{mobile}</td></tr>
                        <tr><td style="padding: 8px 0; color: #666;">Date of Birth</td><td style="padding: 8px 0;">{date_of_birth}</td></tr>
                        <tr><td style="padding: 8px 0; color: #666;">Age Status</td><td style="padding: 8px 0;">{"Minor (Under 18)" if is_minor else "Adult (18+)"}</td></tr>
                        {"<tr><td style='padding: 8px 0; color: #666;'>Address</td><td style='padding: 8px 0;'>" + address + "</td></tr>" if address else ""}
                    </table>
                </div>
                
                {guardian_section_html}
                
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #c9a96e; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Programmes Selected</h3>
                    <ul style="list-style: none; padding: 0; margin: 0;">
                        {programmes_html}
                    </ul>
                </div>
                
                <div style="background: rgba(255, 255, 255, 0.03); border-radius: 8px; padding: 16px; margin-top: 24px;">
                    <p style="color: #666; font-size: 12px; margin: 0; text-align: center;">
                        Review this application in the Admin Dashboard
                    </p>
                </div>
            </div>
        </div>
        """
        
        text_body = f"""
CHANKARTS MUSIC ACADEMY
NEW REGISTRATION APPLICATION

Request ID: {request_id}
Submitted: {submitted_at}
Review Deadline: {review_deadline}
Status: Pending Approval

STUDENT INFORMATION
--------------------
Name: {full_name}
Email: {email}
Mobile: {mobile}
Date of Birth: {date_of_birth}
Age Status: {"Minor (Under 18)" if is_minor else "Adult (18+)"}
{f"Address: {address}" if address else ""}
{guardian_section_text}
PROGRAMMES SELECTED
-------------------
{programmes_text}

---
Review this application in the Admin Dashboard
"""
        
        subject = f"New ChankArts Music Academy Registration — {full_name}"
        return self._send_web3forms(self.admin_email, subject, html_body, text_body)
    
    def send_student_confirmation(
        self,
        to_email: str,
        full_name: str,
        request_id: str,
        submitted_at: str,
    ) -> bool:
        """Send confirmation email to student after registration."""
        
        html_body = f"""
        <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0f17; color: #f5f5f5; border-radius: 12px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 32px; text-align: center; border-bottom: 2px solid #c9a96e;">
                <h1 style="color: #c9a96e; font-size: 20px; margin: 0 0 8px 0; letter-spacing: 0.1em;">CHANKARTS MUSIC ACADEMY</h1>
                <p style="color: #b8b8b8; font-size: 13px; margin: 0; font-style: italic;">Learn. Create. Perform.</p>
            </div>
            
            <div style="padding: 32px;">
                <div style="text-align: center; margin-bottom: 24px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">✓</div>
                    <h2 style="color: #4ade80; font-size: 20px; margin: 0 0 8px 0;">Registration Received</h2>
                    <p style="color: #b8b8b8; font-size: 14px; margin: 0;">Thank you, {full_name}</p>
                </div>
                
                <div style="background: rgba(201, 169, 110, 0.1); border: 1px solid rgba(201, 169, 110, 0.2); border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Application ID:</strong> {request_id}</p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Submitted:</strong> {submitted_at}</p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Status:</strong> <span style="color: #fbbf24;">Pending Approval</span></p>
                    <p style="margin: 4px 0; font-size: 13px;"><strong>Expected Review:</strong> Within 72 hours</p>
                </div>
                
                <p style="color: #b8b8b8; font-size: 14px; line-height: 1.6; text-align: center;">
                    Your application has been successfully received and is now under review. 
                    We will contact you once your registration has been reviewed.
                </p>
                
                <div style="text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid rgba(255, 255, 255, 0.05);">
                    <p style="color: #666; font-size: 12px; margin: 0;">
                        ChankArts Music Academy — Learn. Create. Perform.
                    </p>
                </div>
            </div>
        </div>
        """
        
        text_body = f"""
CHANKARTS MUSIC ACADEMY

Registration Received

Thank you, {full_name}

Application ID: {request_id}
Submitted: {submitted_at}
Status: Pending Approval
Expected Review: Within 72 hours

Your application has been successfully received and is now under review.
We will contact you once your registration has been reviewed.

---
ChankArts Music Academy — Learn. Create. Perform.
"""
        
        subject = f"ChankArts Music Academy — Registration Received ({request_id})"
        return self._send_web3forms(to_email, subject, html_body, text_body)
    
    def send_verification_email(
        self,
        to_email: str,
        full_name: str,
        verify_url: str,
        expires_hours: int = 24,
    ) -> bool:
        """Send email verification link to student."""
        
        html_body = f"""
        <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; background: #0f0f17; color: #f5f5f5; border-radius: 12px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 32px; text-align: center; border-bottom: 2px solid #c9a96e;">
                <h1 style="color: #c9a96e; font-size: 20px; margin: 0 0 8px 0; letter-spacing: 0.1em;">CHANKARTS MUSIC ACADEMY</h1>
                <p style="color: #b8b8b8; font-size: 13px; margin: 0; font-style: italic;">Learn. Create. Perform.</p>
            </div>
            
            <div style="padding: 32px;">
                <div style="text-align: center; margin-bottom: 24px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">✉</div>
                    <h2 style="color: #c9a96e; font-size: 20px; margin: 0 0 8px 0;">Verify Your Email</h2>
                    <p style="color: #b8b8b8; font-size: 14px; margin: 0;">Hello, {full_name}</p>
                </div>
                
                <p style="color: #b8b8b8; font-size: 14px; line-height: 1.6; text-align: center; margin-bottom: 24px;">
                    Please verify your email address by clicking the button below. This helps us confirm your registration details.
                </p>
                
                <div style="text-align: center; margin-bottom: 24px;">
                    <a href="{verify_url}" style="display: inline-block; background: #c9a96e; color: #0f0f17; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 15px;">Verify Email Address</a>
                </div>
                
                <p style="color: #666; font-size: 12px; text-align: center; line-height: 1.6; margin-bottom: 16px;">
                    This verification link expires in {expires_hours} hours.<br>
                    If you did not register at ChankArts Music Academy, please ignore this email.
                </p>
                
                <div style="text-align: center; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.05);">
                    <p style="color: #666; font-size: 12px; margin: 0;">
                        ChankArts Music Academy — Learn. Create. Perform.
                    </p>
                </div>
            </div>
        </div>
        """
        
        text_body = f"""
CHANKARTS MUSIC ACADEMY

Verify Your Email

Hello, {full_name}

Please verify your email address by visiting the link below:

{verify_url}

This verification link expires in {expires_hours} hours.

If you did not register at ChankArts Music Academy, please ignore this email.

---
ChankArts Music Academy — Learn. Create. Perform.
"""
        
        subject = f"ChankArts Music Academy — Verify Your Email"
        return self._send_web3forms(to_email, subject, html_body, text_body)

    # ------------------------------------------------------------------
    # Generic + lifecycle emails
    # ------------------------------------------------------------------
    def send_simple_email(self, to_email: str, subject: str, text_body: str) -> bool:
        """Plain-text/HTML email used for notifications and lifecycle events."""
        html_body = (
            "<div style=\"font-family: Inter, Arial, sans-serif; max-width: 600px; margin: 0 auto;\">"
            f"<h2 style='color:#B58A35;'>{subject}</h2>"
            f"<pre style='white-space:pre-wrap;font-family:inherit;'>{text_body}</pre>"
            "<p style='color:#706B60;font-size:12px;'>ChankArts Music Academy — Learn. Create. Perform.</p>"
            "</div>"
        )
        return self._send_web3forms(to_email, subject, html_body, text_body)

    def send_registration_approved(
        self,
        to_email: str,
        full_name: str,
        cma_registration_id: str,
        programmes: list[str],
        portal_url: str,
    ) -> bool:
        programme_list = ", ".join(programmes) if programmes else "—"
        text_body = f"""
CHANKARTS MUSIC ACADEMY — Registration Approved

Dear {full_name},

Congratulations! Your registration has been approved.

CMA Registration ID: {cma_registration_id}
Programmes: {programme_list}

You can now sign in to the student/parent portal:
{portal_url}

Sign in with your registered email address and the password you created.
If you did not set a password, use "Forgot Password?" on the login page to create one.

---
ChankArts Music Academy — Learn. Create. Perform.
"""
        subject = f"ChankArts Music Academy — Registration Approved ({cma_registration_id})"
        return self._send_web3forms(to_email, subject, self._simple_html(subject, text_body), text_body)

    def send_registration_closed(
        self,
        to_email: str,
        full_name: str,
        status_label: str,
        reason: str,
    ) -> bool:
        text_body = f"""
CHANKARTS MUSIC ACADEMY — Application Update

Dear {full_name},

Your registration application has been updated to: {status_label}

{f"Note from the academy: {reason}" if reason else ""}

If you have questions, please reply to this email or contact the academy.

---
ChankArts Music Academy — Learn. Create. Perform.
"""
        subject = f"ChankArts Music Academy — Application Update ({status_label})"
        return self._send_web3forms(to_email, subject, self._simple_html(subject, text_body), text_body)

    @staticmethod
    def _simple_html(subject: str, text_body: str) -> str:
        escaped = (
            text_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return (
            "<div style=\"font-family: Inter, Arial, sans-serif; max-width: 600px; margin: 0 auto; "
            "background:#FFFFFF; padding:32px;\">"
            f"<h2 style='color:#B58A35;margin:0 0 16px;'>{subject}</h2>"
            f"<pre style='white-space:pre-wrap;font-family:inherit;color:#171815;'>{escaped}</pre>"
            "<p style='color:#706B60;font-size:12px;margin-top:24px;'>"
            "ChankArts Music Academy — Learn. Create. Perform.</p></div>"
        )


# Singleton instance
email_service = EmailService()
