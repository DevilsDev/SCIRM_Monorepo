"""
Integration tests for SCIRM agent workflow
Tests the complete flow from risk assessment creation to recommendation generation
"""

import pytest
import asyncio
import httpx
from typing import Dict, Any
import uuid


class TestAgentWorkflow:
    """Test complete agent workflow integration"""

    @pytest.fixture
    def base_urls(self):
        """Base URLs for all services"""
        return {
            "api_gateway": "http://localhost:8000",
            "coordinator": "http://localhost:8001",
            "planner": "http://localhost:8002",
            "researcher": "http://localhost:8003",
            "executor": "http://localhost:8004",
            "reviewer": "http://localhost:8005"
        }

    @pytest.fixture
    def sample_risk_assessment(self):
        """Sample risk assessment data"""
        return {
            "title": "Supply Chain Disruption - Hurricane Impact",
            "description": "Potential hurricane threatening key supplier facilities in Florida",
            "severity": "high",
            "organization_id": str(uuid.uuid4()),
            "metadata": {
                "location": "Florida, USA",
                "supplier_count": 5,
                "critical_components": ["semiconductors", "packaging materials"]
            }
        }

    @pytest.mark.asyncio
    async def test_complete_workflow(self, base_urls, sample_risk_assessment):
        """Test complete workflow from assessment to recommendations"""
        async with httpx.AsyncClient() as client:
            # Step 1: Create risk assessment via API Gateway
            response = await client.post(
                f"{base_urls['api_gateway']}/api/v1/assessments",
                json=sample_risk_assessment
            )
            assert response.status_code == 201
            assessment_data = response.json()
            assessment_id = assessment_data["id"]

            # Step 2: Trigger coordinator workflow
            response = await client.post(
                f"{base_urls['coordinator']}/process",
                json={"assessment_id": assessment_id}
            )
            assert response.status_code == 200
            task_data = response.json()
            task_id = task_data["task_id"]

            # Step 3: Wait for workflow completion (with timeout)
            max_wait = 60  # seconds
            wait_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                response = await client.get(
                    f"{base_urls['coordinator']}/tasks/{task_id}/status"
                )
                assert response.status_code == 200
                status_data = response.json()
                
                if status_data["status"] == "completed":
                    break
                elif status_data["status"] == "failed":
                    pytest.fail(f"Workflow failed: {status_data.get('error')}")
                
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

            assert elapsed < max_wait, "Workflow timed out"

            # Step 4: Verify final assessment has recommendations
            response = await client.get(
                f"{base_urls['api_gateway']}/api/v1/assessments/{assessment_id}"
            )
            assert response.status_code == 200
            final_assessment = response.json()
            
            assert final_assessment["status"] == "completed"
            assert "recommendations" in final_assessment
            assert len(final_assessment["recommendations"]) > 0
            assert final_assessment["confidence_score"] > 0.7

    @pytest.mark.asyncio
    async def test_planner_agent_integration(self, base_urls, sample_risk_assessment):
        """Test Planner agent CAG functionality"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_urls['planner']}/plan",
                json={
                    "assessment": sample_risk_assessment,
                    "organization_context": {
                        "industry": "pharmaceutical",
                        "compliance_requirements": ["FDA", "GMP"],
                        "risk_tolerance": "low"
                    }
                }
            )
            
            assert response.status_code == 200
            plan_data = response.json()
            
            assert "plan" in plan_data
            assert "priority_score" in plan_data
            assert "reasoning" in plan_data
            assert plan_data["confidence_score"] > 0.5

    @pytest.mark.asyncio
    async def test_researcher_agent_integration(self, base_urls):
        """Test Researcher agent RAG functionality"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_urls['researcher']}/research",
                json={
                    "query": "hurricane impact supply chain Florida semiconductors",
                    "data_sources": ["weather", "logistics", "news"],
                    "max_results": 10
                }
            )
            
            assert response.status_code == 200
            research_data = response.json()
            
            assert "research_results" in research_data
            assert "confidence_score" in research_data
            assert "data_sources_used" in research_data
            assert len(research_data["research_results"]) > 0

    @pytest.mark.asyncio
    async def test_executor_agent_integration(self, base_urls, sample_risk_assessment):
        """Test Executor agent recommendation generation"""
        async with httpx.AsyncClient() as client:
            # Mock research data
            research_data = {
                "research_results": [
                    {
                        "source": "weather",
                        "data": "Hurricane Category 3 approaching Florida coast",
                        "confidence": 0.95
                    }
                ]
            }
            
            response = await client.post(
                f"{base_urls['executor']}/execute",
                json={
                    "assessment": sample_risk_assessment,
                    "research_data": research_data,
                    "organization_context": {
                        "budget_constraints": 1000000,
                        "timeline_constraints": 30
                    }
                }
            )
            
            assert response.status_code == 200
            execution_data = response.json()
            
            assert "recommendations" in execution_data
            assert len(execution_data["recommendations"]) > 0
            
            for rec in execution_data["recommendations"]:
                assert "title" in rec
                assert "estimated_cost" in rec
                assert "priority" in rec
                assert "timeline_days" in rec

    @pytest.mark.asyncio
    async def test_reviewer_agent_integration(self, base_urls):
        """Test Reviewer agent quality validation"""
        async with httpx.AsyncClient() as client:
            # Mock assessment and recommendations
            review_data = {
                "assessment": {
                    "title": "Test Assessment",
                    "severity": "high",
                    "confidence_score": 0.85
                },
                "recommendations": [
                    {
                        "title": "Emergency supplier diversification",
                        "priority": 1,
                        "estimated_cost": 500000,
                        "timeline_days": 14
                    }
                ],
                "compliance_requirements": ["FDA", "GMP"]
            }
            
            response = await client.post(
                f"{base_urls['reviewer']}/review",
                json=review_data
            )
            
            assert response.status_code == 200
            review_result = response.json()
            
            assert "approval_status" in review_result
            assert "quality_score" in review_result
            assert "compliance_status" in review_result
            assert "review_comments" in review_result

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, base_urls):
        """Test error handling in agent workflow"""
        async with httpx.AsyncClient() as client:
            # Test with invalid assessment data
            invalid_assessment = {
                "title": "",  # Invalid empty title
                "severity": "invalid_severity"  # Invalid severity
            }
            
            response = await client.post(
                f"{base_urls['api_gateway']}/api/v1/assessments",
                json=invalid_assessment
            )
            
            assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_concurrent_workflows(self, base_urls, sample_risk_assessment):
        """Test handling multiple concurrent workflows"""
        async with httpx.AsyncClient() as client:
            # Create multiple assessments concurrently
            tasks = []
            for i in range(3):
                assessment = sample_risk_assessment.copy()
                assessment["title"] = f"Concurrent Test {i}"
                
                task = client.post(
                    f"{base_urls['api_gateway']}/api/v1/assessments",
                    json=assessment
                )
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_health_checks(self, base_urls):
        """Test health endpoints for all services"""
        async with httpx.AsyncClient() as client:
            for service, url in base_urls.items():
                response = await client.get(f"{url}/health")
                assert response.status_code == 200
                health_data = response.json()
                assert health_data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_metrics_endpoints(self, base_urls):
        """Test metrics endpoints for monitoring"""
        async with httpx.AsyncClient() as client:
            for service, url in base_urls.items():
                response = await client.get(f"{url}/metrics")
                assert response.status_code == 200
                # Metrics should be in Prometheus format
                assert "# HELP" in response.text or "# TYPE" in response.text
