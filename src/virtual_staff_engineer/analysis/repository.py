import hashlib

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.analysis.orchestrator import AnalysisResult
from virtual_staff_engineer.database.connection import connect


class AnalysisRepository:
    """Transactional PostgreSQL persistence for Phase 2 audit records."""

    def __init__(self, database_url=None):
        self.database_url = database_url

    def create_run(
        self,
        analysis_input,
        model_name,
        workflow_version,
        prompt_version,
    ):
        if not isinstance(analysis_input, AnalysisInput):
            raise TypeError("analysis_input must be an AnalysisInput.")
        input_checksum = hashlib.sha256(
            analysis_input.content.encode("utf-8")
        ).hexdigest()

        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analysis_runs (
                        commit_id,
                        status,
                        model_name,
                        workflow_version,
                        prompt_version,
                        started_at,
                        input_type,
                        source_path,
                        input_content,
                        input_checksum
                    )
                    VALUES (
                        %s,
                        'analyzing',
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING analysis_run_id;
                    """,
                    (
                        analysis_input.commit_id,
                        model_name,
                        workflow_version,
                        prompt_version,
                        analysis_input.input_type,
                        analysis_input.source_path,
                        analysis_input.content,
                        input_checksum,
                    ),
                )
                return str(cur.fetchone()[0])

    def complete_run(
        self,
        analysis_run_id,
        result,
        input_tokens=0,
        output_tokens=0,
    ):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                self.persist_result(
                    cur,
                    analysis_run_id,
                    result,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

    def persist_result(
        self,
        cur,
        analysis_run_id,
        result,
        input_tokens=0,
        output_tokens=0,
    ):
        """Persist a result using the caller's existing transaction."""
        if not isinstance(result, AnalysisResult):
            raise TypeError("result must be an AnalysisResult.")
        self._validate_result_consistency(result)

        evidence_by_chunk = {
            item.playbook_chunk_id: item for item in result.evidence
        }
        decision_by_index = {
            decision.finding_index: decision for decision in result.decisions
        }

        query_ids = self._insert_queries(
            cur, analysis_run_id, result.queries
        )
        self._insert_retrieval_evidence(cur, query_ids, result.evidence)
        self._insert_playbook_versions(
            cur, analysis_run_id, result.evidence
        )
        finding_ids = self._insert_finding_reviews(
            cur,
            analysis_run_id,
            result.evaluated_findings,
            decision_by_index,
        )
        self._insert_violations(
            cur,
            analysis_run_id,
            result.evaluated_findings,
            decision_by_index,
            finding_ids,
            evidence_by_chunk,
            persist_supported=result.status == "review_required",
        )
        self._insert_rejections(
            cur, analysis_run_id, result.rejected_findings
        )
        cur.execute(
            """
            UPDATE analysis_runs
            SET
                status = %s,
                completed_at = CURRENT_TIMESTAMP,
                input_tokens = %s,
                output_tokens = %s,
                tool_call_count = %s,
                inconclusive_reason = %s,
                error_message = NULL
            WHERE analysis_run_id = %s
              AND status = 'analyzing';
            """,
            (
                result.status,
                input_tokens,
                output_tokens,
                len(result.queries),
                result.inconclusive_reason,
                analysis_run_id,
            ),
        )
        if cur.rowcount != 1:
            raise ValueError(
                "Analysis run is missing or is not in analyzing state."
            )

    def fail_run(self, analysis_run_id, error_message):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE analysis_runs
                    SET
                        status = 'failed',
                        completed_at = CURRENT_TIMESTAMP,
                        error_message = %s
                    WHERE analysis_run_id = %s
                      AND status = 'analyzing';
                    """,
                    (str(error_message)[:4000], analysis_run_id),
                )

    @staticmethod
    def _insert_queries(cur, analysis_run_id, queries):
        query_ids = {}
        for sequence, query in enumerate(queries, start=1):
            cur.execute(
                """
                INSERT INTO analysis_run_queries (
                    analysis_run_id,
                    query_sequence,
                    query_text,
                    purpose
                )
                VALUES (%s, %s, %s, %s)
                RETURNING analysis_query_id;
                """,
                (analysis_run_id, sequence, query.query, query.purpose),
            )
            query_ids[query.query] = cur.fetchone()[0]
        return query_ids

    @staticmethod
    def _insert_retrieval_evidence(cur, query_ids, evidence):
        for item in evidence:
            query_id = query_ids.get(item.retrieval_query)
            if query_id is None:
                raise ValueError(
                    "Evidence references a query that was not executed."
                )
            cur.execute(
                """
                INSERT INTO analysis_retrieval_evidence (
                    analysis_query_id,
                    playbook_chunk_id,
                    rank_position,
                    retrieval_score,
                    semantic_rank,
                    lexical_rank,
                    rule_snapshot
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    query_id,
                    item.playbook_chunk_id,
                    item.rank_position,
                    item.retrieval_score,
                    item.semantic_rank,
                    item.lexical_rank,
                    item.content,
                ),
            )

    @staticmethod
    def _insert_playbook_versions(cur, analysis_run_id, evidence):
        version_ids = sorted(
            {item.playbook_version_id for item in evidence}
        )
        for playbook_version_id in version_ids:
            cur.execute(
                """
                INSERT INTO analysis_run_playbook_versions (
                    analysis_run_id,
                    playbook_version_id
                )
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
                """,
                (analysis_run_id, playbook_version_id),
            )

    @staticmethod
    def _insert_finding_reviews(
        cur,
        analysis_run_id,
        findings,
        decision_by_index,
    ):
        finding_ids = {}
        for finding_index, finding in enumerate(findings):
            decision = decision_by_index.get(finding_index)
            verdict = decision.verdict if decision else "undecided"
            evaluator_reason = decision.reason if decision else None
            cur.execute(
                """
                INSERT INTO analysis_finding_reviews (
                    analysis_run_id,
                    finding_index,
                    playbook_chunk_id,
                    rule_key,
                    source_path,
                    start_line,
                    end_line,
                    input_excerpt,
                    explanation,
                    severity,
                    confidence,
                    verdict,
                    evaluator_reason
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                RETURNING analysis_finding_id;
                """,
                (
                    analysis_run_id,
                    finding_index,
                    finding.playbook_chunk_id,
                    finding.rule_key,
                    finding.source_path,
                    finding.start_line,
                    finding.end_line,
                    finding.input_excerpt,
                    finding.explanation,
                    finding.severity,
                    finding.confidence,
                    verdict,
                    evaluator_reason,
                ),
            )
            finding_ids[finding_index] = cur.fetchone()[0]
        return finding_ids

    @staticmethod
    def _insert_violations(
        cur,
        analysis_run_id,
        findings,
        decision_by_index,
        finding_ids,
        evidence_by_chunk,
        persist_supported,
    ):
        if not persist_supported:
            return
        for finding_index, finding in enumerate(findings):
            decision = decision_by_index.get(finding_index)
            if decision is None or decision.verdict != "supported":
                continue
            evidence = evidence_by_chunk[finding.playbook_chunk_id]
            cur.execute(
                """
                INSERT INTO violations (
                    analysis_run_id,
                    analysis_finding_id,
                    file_path,
                    start_line,
                    end_line,
                    severity,
                    explanation,
                    confidence,
                    validation_status,
                    input_excerpt
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, 'valid', %s
                )
                RETURNING violation_id;
                """,
                (
                    analysis_run_id,
                    finding_ids[finding_index],
                    finding.source_path,
                    finding.start_line,
                    finding.end_line,
                    finding.severity,
                    finding.explanation,
                    finding.confidence,
                    finding.input_excerpt,
                ),
            )
            violation_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO violation_evidence (
                    violation_id,
                    playbook_chunk_id,
                    rule_snapshot,
                    retrieval_score,
                    rank_position
                )
                VALUES (%s, %s, %s, %s, %s);
                """,
                (
                    violation_id,
                    evidence.playbook_chunk_id,
                    evidence.content,
                    evidence.retrieval_score,
                    evidence.rank_position,
                ),
            )

    @staticmethod
    def _insert_rejections(cur, analysis_run_id, rejections):
        for rejection in rejections:
            finding = rejection.finding
            cur.execute(
                """
                INSERT INTO analysis_finding_rejections (
                    analysis_run_id,
                    finding_index,
                    rejection_code,
                    rejection_reason,
                    cited_playbook_chunk_id,
                    rule_key,
                    source_path,
                    start_line,
                    end_line,
                    input_excerpt,
                    explanation,
                    severity,
                    confidence
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                );
                """,
                (
                    analysis_run_id,
                    rejection.finding_index,
                    rejection.code,
                    rejection.reason,
                    finding.playbook_chunk_id,
                    finding.rule_key,
                    finding.source_path,
                    finding.start_line,
                    finding.end_line,
                    finding.input_excerpt,
                    finding.explanation,
                    finding.severity,
                    finding.confidence,
                ),
            )

    @staticmethod
    def _validate_result_consistency(result):
        decision_by_index = {
            decision.finding_index: decision for decision in result.decisions
        }
        supported = tuple(
            finding
            for finding_index, finding in enumerate(result.evaluated_findings)
            if finding_index in decision_by_index
            and decision_by_index[finding_index].verdict == "supported"
        )
        expected = supported if result.status == "review_required" else ()
        if result.findings != expected:
            raise ValueError(
                "Analysis result findings do not match evaluator decisions."
            )
