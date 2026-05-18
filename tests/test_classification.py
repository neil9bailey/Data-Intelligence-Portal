from sqlmodel import select

from app.classification import agent_classify_catalogue
from app.models import AuditEvent, Customer, ExtractedQualityQuestion, ExtractedRequirement, Opportunity
from app.requirement_taxonomy import classify_requirement_category


def test_agent_auto_assigns_and_approves_high_confidence_opportunity(seeded_session):
    opportunity = Opportunity(
        title="National Highways roadside cyber resilience framework",
        buyer_name="National Highways Limited",
        source_url="https://www.find-tender.service.gov.uk/Notice/test-agent",
        summary="Roadside operational technology, SCADA, cyber security and service continuity.",
        status="new",
        relevance_score=86,
    )
    seeded_session.add(opportunity)
    seeded_session.commit()
    seeded_session.refresh(opportunity)

    result = agent_classify_catalogue(seeded_session)
    seeded_session.commit()
    seeded_session.refresh(opportunity)
    customer = seeded_session.exec(select(Customer).where(Customer.customer_name == "National Highways")).first()

    assert result["auto_approved"] >= 1
    assert opportunity.status == "approved"
    assert opportunity.customer_id == customer.id
    assert opportunity.business_unit_id == customer.business_unit_id
    assert seeded_session.exec(select(AuditEvent).where(AuditEvent.action == "agent_classify")).first() is not None


def test_requirement_taxonomy_categorises_requirements_and_questions(seeded_session):
    opportunity = seeded_session.exec(select(Opportunity)).first()
    requirement = ExtractedRequirement(
        opportunity_id=opportunity.id,
        requirement_theme="cyber security",
        requirement_text="Supplier must describe cyber security accreditation and SOC response for roadside systems.",
        confidence="high",
        human_review_status="pending",
    )
    question = ExtractedQualityQuestion(
        opportunity_id=opportunity.id,
        question_text="Describe your API integration, reporting dashboard and analytics approach.",
        requirement_theme="data and analytics",
        confidence="medium",
        human_review_status="pending",
    )
    seeded_session.add(requirement)
    seeded_session.add(question)
    seeded_session.commit()

    result = agent_classify_catalogue(seeded_session)
    seeded_session.commit()
    seeded_session.refresh(requirement)
    seeded_session.refresh(question)

    assert classify_requirement_category(requirement.requirement_text, requirement.requirement_theme) == "cyber_and_information_security"
    assert requirement.requirement_category == "cyber_and_information_security"
    assert question.requirement_category == "digital_data_and_integration"
    assert requirement.human_review_status == "approved"
    assert question.human_review_status == "approved"
    assert result["requirements"] >= 1
    assert result["questions"] >= 1

