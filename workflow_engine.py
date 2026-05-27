# workflow_engine.py - Workflow automation and rules engine
import json
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timedelta
from enum import Enum
from structured_logging import get_logger

logger = get_logger("workflow_engine")

class WorkflowTrigger(Enum):
    """Workflow trigger types"""
    CUSTOMER_CREATED = "customer_created"
    CUSTOMER_UPDATED = "customer_updated"
    TICKET_CREATED = "ticket_created"
    TICKET_STATUS_CHANGED = "ticket_status_changed"
    DEAL_STAGE_CHANGED = "deal_stage_changed"
    EMAIL_RECEIVED = "email_received"
    TIME_BASED = "time_based"

class WorkflowAction(Enum):
    """Workflow actions"""
    SEND_EMAIL = "send_email"
    CREATE_TICKET = "create_ticket"
    UPDATE_CUSTOMER = "update_customer"
    ADD_TASK = "add_task"
    SEND_SLACK = "send_slack"
    CREATE_DEAL = "create_deal"
    ESCALATE_TICKET = "escalate_ticket"
    LOG_ACTIVITY = "log_activity"

class WorkflowRule:
    """Automation rule"""
    
    def __init__(
        self,
        name: str,
        trigger: WorkflowTrigger,
        condition: Callable,
        actions: List[Dict[str, Any]],
        enabled: bool = True
    ):
        self.name = name
        self.trigger = trigger
        self.condition = condition
        self.actions = actions
        self.enabled = enabled
        self.created_at = datetime.utcnow()
        self.executions = 0

class WorkflowEngine:
    """Workflow automation engine"""
    
    def __init__(self):
        self.rules: List[WorkflowRule] = []
        self.action_handlers: Dict[WorkflowAction, Callable] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default action handlers"""
        self.action_handlers = {
            WorkflowAction.SEND_EMAIL: self._handle_send_email,
            WorkflowAction.CREATE_TICKET: self._handle_create_ticket,
            WorkflowAction.UPDATE_CUSTOMER: self._handle_update_customer,
            WorkflowAction.ADD_TASK: self._handle_add_task,
            WorkflowAction.SEND_SLACK: self._handle_send_slack,
            WorkflowAction.CREATE_DEAL: self._handle_create_deal,
            WorkflowAction.ESCALATE_TICKET: self._handle_escalate_ticket,
            WorkflowAction.LOG_ACTIVITY: self._handle_log_activity,
        }
    
    def register_rule(
        self,
        name: str,
        trigger: WorkflowTrigger,
        condition: Callable,
        actions: List[Dict[str, Any]]
    ) -> WorkflowRule:
        """Register a workflow rule"""
        rule = WorkflowRule(name, trigger, condition, actions)
        self.rules.append(rule)
        logger.info(f"Workflow rule registered: {name}")
        return rule
    
    async def execute(
        self,
        trigger: WorkflowTrigger,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute workflows for trigger"""
        results = []
        
        for rule in self.rules:
            if not rule.enabled or rule.trigger != trigger:
                continue
            
            try:
                # Check condition
                if not rule.condition(context):
                    continue
                
                logger.info(f"Executing workflow rule: {rule.name}", context=context)
                
                # Execute actions
                for action in rule.actions:
                    result = await self._execute_action(action, context)
                    results.append(result)
                
                rule.executions += 1
            
            except Exception as e:
                logger.error(f"Error executing workflow rule: {rule.name}", error=str(e))
                results.append({
                    "action": "error",
                    "rule": rule.name,
                    "error": str(e)
                })
        
        return results
    
    async def _execute_action(
        self,
        action: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single action"""
        action_type = WorkflowAction(action["type"])
        handler = self.action_handlers.get(action_type)
        
        if not handler:
            logger.warning(f"No handler for action type: {action_type}")
            return {"action": action_type.value, "status": "no_handler"}
        
        return await handler(action, context)
    
    # Action handlers
    async def _handle_send_email(self, action: Dict, context: Dict) -> Dict:
        """Handle send email action"""
        logger.info("Sending email", recipient=action.get("to"))
        # Implementation
        return {"action": "send_email", "status": "queued"}
    
    async def _handle_create_ticket(self, action: Dict, context: Dict) -> Dict:
        """Handle create ticket action"""
        logger.info("Creating ticket", customer_id=context.get("customer_id"))
        # Implementation
        return {"action": "create_ticket", "status": "created"}
    
    async def _handle_update_customer(self, action: Dict, context: Dict) -> Dict:
        """Handle update customer action"""
        logger.info("Updating customer", customer_id=context.get("customer_id"))
        # Implementation
        return {"action": "update_customer", "status": "updated"}
    
    async def _handle_add_task(self, action: Dict, context: Dict) -> Dict:
        """Handle add task action"""
        logger.info("Adding task", title=action.get("title"))
        # Implementation
        return {"action": "add_task", "status": "created"}
    
    async def _handle_send_slack(self, action: Dict, context: Dict) -> Dict:
        """Handle send Slack action"""
        logger.info("Sending Slack message", channel=action.get("channel"))
        # Implementation
        return {"action": "send_slack", "status": "sent"}
    
    async def _handle_create_deal(self, action: Dict, context: Dict) -> Dict:
        """Handle create deal action"""
        logger.info("Creating deal", customer_id=context.get("customer_id"))
        # Implementation
        return {"action": "create_deal", "status": "created"}
    
    async def _handle_escalate_ticket(self, action: Dict, context: Dict) -> Dict:
        """Handle escalate ticket action"""
        logger.info("Escalating ticket", ticket_id=context.get("ticket_id"))
        # Implementation
        return {"action": "escalate_ticket", "status": "escalated"}
    
    async def _handle_log_activity(self, action: Dict, context: Dict) -> Dict:
        """Handle log activity action"""
        logger.info("Logging activity", activity=action.get("message"))
        # Implementation
        return {"action": "log_activity", "status": "logged"}

# Global workflow engine instance
_workflow_engine = None

def get_workflow_engine() -> WorkflowEngine:
    """Get workflow engine instance"""
    global _workflow_engine
    if not _workflow_engine:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine

def init_workflows():
    """Initialize default workflows"""
    engine = get_workflow_engine()
    
    # Workflow 1: Auto-create ticket from email
    engine.register_rule(
        name="Auto-create ticket from email",
        trigger=WorkflowTrigger.EMAIL_RECEIVED,
        condition=lambda ctx: ctx.get("is_new_email", False),
        actions=[
            {
                "type": WorkflowAction.CREATE_TICKET.value,
                "title_from": "email_subject",
                "description_from": "email_body",
                "customer_id_from": "email_from"
            }
        ]
    )
    
    # Workflow 2: Send welcome email to new customers
    engine.register_rule(
        name="Send welcome email to new customer",
        trigger=WorkflowTrigger.CUSTOMER_CREATED,
        condition=lambda ctx: True,
        actions=[
            {
                "type": WorkflowAction.SEND_EMAIL.value,
                "to_from": "customer_email",
                "template": "welcome",
                "subject": "Welcome to Mr.Holmes CRM"
            }
        ]
    )
    
    # Workflow 3: Escalate old tickets
    engine.register_rule(
        name="Escalate old tickets",
        trigger=WorkflowTrigger.TIME_BASED,
        condition=lambda ctx: ctx.get("ticket_age_hours", 0) > 24,
        actions=[
            {
                "type": WorkflowAction.ESCALATE_TICKET.value,
                "priority": "high"
            },
            {
                "type": WorkflowAction.SEND_SLACK.value,
                "channel": "#tickets",
                "message": "Old ticket needs attention"
            }
        ]
    )
