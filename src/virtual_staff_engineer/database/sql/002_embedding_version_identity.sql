ALTER TABLE playbook_versions
    DROP CONSTRAINT playbook_versions_document_checksum_uq;

ALTER TABLE playbook_versions
    ADD CONSTRAINT playbook_versions_document_embedding_uq
    UNIQUE (
        document_id,
        checksum,
        embedding_model,
        embedding_dimension
    );
