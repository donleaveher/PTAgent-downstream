"""实验事实库的 MySQL 8+ schema。"""

from __future__ import annotations


MYSQL_EXPERIMENT_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS experiment_context (
      experiment_id VARCHAR(64) PRIMARY KEY,
      session_id VARCHAR(64) NULL,
      title VARCHAR(512) NOT NULL,
      raw_text LONGTEXT NOT NULL,
      disease_json JSON NOT NULL,
      pathway_json JSON NOT NULL,
      organism VARCHAR(255) NOT NULL,
      taxon_id BIGINT NULL,
      assay VARCHAR(255) NOT NULL,
      design_json JSON NOT NULL,
      current_request_id VARCHAR(64) NULL,
      status VARCHAR(32) NOT NULL,
      created_at DATETIME(6) NOT NULL,
      updated_at DATETIME(6) NOT NULL,
      INDEX idx_experiment_session (session_id),
      INDEX idx_experiment_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_request (
      request_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      version INT NOT NULL,
      raw_question LONGTEXT NOT NULL,
      request_payload_json JSON NOT NULL,
      submitted_by VARCHAR(128) NULL,
      submitted_at DATETIME(6) NOT NULL,
      content_hash CHAR(64) NOT NULL,
      supersedes_request_id VARCHAR(64) NULL,
      UNIQUE KEY uq_experiment_request_version (experiment_id, version),
      INDEX idx_request_experiment_time (experiment_id, submitted_at),
      CONSTRAINT fk_request_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE,
      CONSTRAINT fk_request_supersedes FOREIGN KEY (supersedes_request_id)
        REFERENCES experiment_request(request_id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_input_artifact (
      input_artifact_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      request_id VARCHAR(64) NOT NULL,
      object_id VARCHAR(128) NOT NULL,
      input_role VARCHAR(64) NOT NULL,
      filename VARCHAR(1024) NOT NULL,
      file_hash VARCHAR(128) NULL,
      file_size BIGINT NULL,
      upstream_software VARCHAR(255) NOT NULL,
      upstream_version VARCHAR(128) NOT NULL,
      created_at DATETIME(6) NOT NULL,
      UNIQUE KEY uq_request_object_role (request_id, object_id, input_role),
      INDEX idx_artifact_experiment (experiment_id),
      CONSTRAINT fk_artifact_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE,
      CONSTRAINT fk_artifact_request FOREIGN KEY (request_id)
        REFERENCES experiment_request(request_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_context_revision (
      revision_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      request_id VARCHAR(64) NOT NULL,
      structured_context_json JSON NOT NULL,
      parser_version VARCHAR(128) NOT NULL,
      model_version VARCHAR(128) NULL,
      confirmation_status VARCHAR(32) NOT NULL,
      confirmed_by VARCHAR(128) NULL,
      parsed_at DATETIME(6) NOT NULL,
      INDEX idx_revision_request_time (request_id, parsed_at),
      CONSTRAINT fk_revision_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE,
      CONSTRAINT fk_revision_request FOREIGN KEY (request_id)
        REFERENCES experiment_request(request_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_group (
      experiment_id VARCHAR(64) NOT NULL,
      group_id VARCHAR(128) NOT NULL,
      label VARCHAR(255) NOT NULL,
      role VARCHAR(32) NOT NULL,
      meta_json JSON NOT NULL,
      PRIMARY KEY (experiment_id, group_id),
      UNIQUE KEY uq_experiment_group_label (experiment_id, label),
      CONSTRAINT fk_group_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS protein (
      experiment_id VARCHAR(64) NOT NULL,
      protein_id VARCHAR(128) NOT NULL,
      accession VARCHAR(128) NOT NULL,
      gene_symbol VARCHAR(128) NOT NULL,
      organism VARCHAR(255) NOT NULL,
      taxon_id BIGINT NULL,
      peptide_ids_json JSON NOT NULL,
      meta_json JSON NOT NULL,
      PRIMARY KEY (experiment_id, protein_id),
      INDEX idx_protein_accession (accession),
      INDEX idx_protein_gene (gene_symbol),
      CONSTRAINT fk_protein_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS structure_evidence_status (
      experiment_id VARCHAR(64) NOT NULL,
      protein_id VARCHAR(128) NOT NULL,
      raw_accession VARCHAR(255) NOT NULL,
      normalized_accession VARCHAR(128) NOT NULL,
      channel VARCHAR(64) NOT NULL,
      status VARCHAR(32) NOT NULL,
      reason VARCHAR(255) NOT NULL,
      provider VARCHAR(128) NOT NULL,
      provider_version VARCHAR(128) NOT NULL,
      structure_id VARCHAR(255) NOT NULL,
      structure_format VARCHAR(32) NOT NULL,
      local_path TEXT NOT NULL,
      object_uri TEXT NOT NULL,
      sha256 VARCHAR(128) NOT NULL,
      meta_json JSON NOT NULL,
      checked_at DATETIME(6) NOT NULL,
      PRIMARY KEY (experiment_id, protein_id, channel),
      INDEX idx_structure_status (experiment_id, status),
      INDEX idx_structure_norm_accession (normalized_accession),
      CONSTRAINT fk_structure_status_protein FOREIGN KEY (experiment_id, protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS structure_search_run (
      run_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      provider VARCHAR(128) NOT NULL,
      provider_version VARCHAR(128) NOT NULL,
      db_version VARCHAR(128) NOT NULL,
      params_hash CHAR(64) NOT NULL,
      params_json JSON NOT NULL,
      status VARCHAR(32) NOT NULL,
      started_at DATETIME(6) NOT NULL,
      finished_at DATETIME(6) NOT NULL,
      meta_json JSON NOT NULL,
      INDEX idx_structure_run_experiment (experiment_id, started_at),
      INDEX idx_structure_run_hash (experiment_id, provider, params_hash),
      CONSTRAINT fk_structure_run_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS structure_neighbor_evidence (
      evidence_id VARCHAR(64) PRIMARY KEY,
      run_id VARCHAR(64) NOT NULL,
      experiment_id VARCHAR(64) NOT NULL,
      query_protein_id VARCHAR(128) NOT NULL,
      query_accession VARCHAR(128) NOT NULL,
      target_accession VARCHAR(128) NOT NULL,
      neighbor_rank INT NOT NULL,
      score DOUBLE NOT NULL,
      coverage DOUBLE NOT NULL,
      taxon_id BIGINT NULL,
      taxon_name VARCHAR(255) NOT NULL,
      relation_id VARCHAR(255) NOT NULL,
      provenance_json JSON NOT NULL,
      created_at DATETIME(6) NOT NULL,
      UNIQUE KEY uq_structure_neighbor_run
        (run_id, query_protein_id, target_accession),
      INDEX idx_structure_neighbor_query (experiment_id, query_protein_id),
      INDEX idx_structure_neighbor_target (target_accession),
      CONSTRAINT fk_structure_neighbor_run FOREIGN KEY (run_id)
        REFERENCES structure_search_run(run_id) ON DELETE CASCADE,
      CONSTRAINT fk_structure_neighbor_protein FOREIGN KEY (experiment_id, query_protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS fused_candidate (
      candidate_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      query_protein_id VARCHAR(128) NOT NULL,
      query_accession VARCHAR(128) NOT NULL,
      target_type VARCHAR(64) NOT NULL,
      target_id VARCHAR(255) NOT NULL,
      relation_type VARCHAR(64) NOT NULL,
      fused_score DOUBLE NOT NULL,
      fusion_rank INT NOT NULL,
      support_channels_json JSON NOT NULL,
      evidence_ids_json JSON NOT NULL,
      projection_status VARCHAR(32) NOT NULL,
      projection_reason VARCHAR(255) NOT NULL,
      meta_json JSON NOT NULL,
      created_at DATETIME(6) NOT NULL,
      UNIQUE KEY uq_fused_candidate_target
        (experiment_id, query_protein_id, relation_type, target_type, target_id),
      INDEX idx_fused_candidate_query
        (experiment_id, query_protein_id, relation_type, fusion_rank),
      INDEX idx_fused_candidate_target (target_type, target_id),
      CONSTRAINT fk_fused_candidate_protein FOREIGN KEY (experiment_id, query_protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS peptide (
      experiment_id VARCHAR(64) NOT NULL,
      peptide_id VARCHAR(128) NOT NULL,
      peptidoform VARCHAR(1024) NOT NULL,
      stripped_sequence VARCHAR(1024) NOT NULL,
      protein_id VARCHAR(128) NOT NULL,
      spectrum_ids_json JSON NOT NULL,
      confidence DOUBLE NOT NULL,
      group_label VARCHAR(255) NOT NULL,
      abundance DOUBLE NULL,
      meta_json JSON NOT NULL,
      PRIMARY KEY (experiment_id, peptide_id),
      INDEX idx_peptide_protein (experiment_id, protein_id),
      INDEX idx_peptide_group (experiment_id, group_label),
      CONSTRAINT fk_peptide_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE,
      CONSTRAINT fk_peptide_protein FOREIGN KEY (experiment_id, protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE,
      CONSTRAINT fk_peptide_group FOREIGN KEY (experiment_id, group_label)
        REFERENCES experiment_group(experiment_id, label) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS protein_quantification (
      quantification_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      protein_id VARCHAR(128) NOT NULL,
      group_id VARCHAR(128) NOT NULL,
      sample_id VARCHAR(128) NOT NULL,
      abundance DOUBLE NOT NULL,
      meta_json JSON NOT NULL,
      UNIQUE KEY uq_protein_quant_sample
        (experiment_id, protein_id, group_id, sample_id),
      CONSTRAINT fk_quant_protein FOREIGN KEY (experiment_id, protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE,
      CONSTRAINT fk_quant_group FOREIGN KEY (experiment_id, group_id)
        REFERENCES experiment_group(experiment_id, group_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS differential_result (
      differential_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      protein_id VARCHAR(128) NOT NULL,
      case_group_id VARCHAR(128) NOT NULL,
      control_group_id VARCHAR(128) NOT NULL,
      log2fc DOUBLE NOT NULL,
      p_value DOUBLE NULL,
      q_value DOUBLE NULL,
      direction VARCHAR(32) NOT NULL,
      is_differential BOOLEAN NOT NULL,
      meta_json JSON NOT NULL,
      UNIQUE KEY uq_differential_comparison
        (experiment_id, protein_id, case_group_id, control_group_id),
      INDEX idx_differential_flag (experiment_id, is_differential),
      CONSTRAINT fk_differential_protein FOREIGN KEY (experiment_id, protein_id)
        REFERENCES protein(experiment_id, protein_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS enrichment_result (
      enrichment_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      term VARCHAR(128) NOT NULL,
      term_name VARCHAR(255) NOT NULL,
      term_type VARCHAR(32) NOT NULL,
      overlap INT NOT NULL,
      study_size INT NOT NULL,
      background_size INT NOT NULL,
      term_size INT NOT NULL,
      p_value DOUBLE NULL,
      q_value DOUBLE NULL,
      fold_enrichment DOUBLE NOT NULL,
      is_significant BOOLEAN NOT NULL,
      gene_set_source VARCHAR(128) NOT NULL,
      gene_set_version VARCHAR(128) NOT NULL,
      study_checksum CHAR(64) NOT NULL,
      background_checksum CHAR(64) NOT NULL,
      meta_json JSON NOT NULL,
      UNIQUE KEY uq_enrichment_term (experiment_id, term_type, term),
      INDEX idx_enrichment_sig (experiment_id, is_significant),
      CONSTRAINT fk_enrichment_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_annotation (
      annotation_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      target VARCHAR(128) NOT NULL,
      target_type VARCHAR(32) NOT NULL,
      attribute VARCHAR(255) NOT NULL,
      value_json JSON NOT NULL,
      evidence_level VARCHAR(32) NOT NULL,
      source VARCHAR(128) NOT NULL,
      derivation_json JSON NOT NULL,
      provenance_json JSON NOT NULL,
      created_at DATETIME(6) NOT NULL,
      updated_at DATETIME(6) NOT NULL,
      INDEX idx_annotation_target (experiment_id, target_type, target),
      INDEX idx_annotation_level (experiment_id, evidence_level),
      CONSTRAINT fk_annotation_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS annotation_history (
      history_id VARCHAR(64) PRIMARY KEY,
      annotation_id VARCHAR(64) NOT NULL,
      experiment_id VARCHAR(64) NOT NULL,
      from_level VARCHAR(32) NULL,
      to_level VARCHAR(32) NOT NULL,
      verdict VARCHAR(64) NOT NULL,
      evidence_ref_json JSON NOT NULL,
      changed_at DATETIME(6) NOT NULL,
      INDEX idx_history_annotation (annotation_id, changed_at),
      CONSTRAINT fk_history_annotation FOREIGN KEY (annotation_id)
        REFERENCES meta_annotation(annotation_id) ON DELETE CASCADE,
      CONSTRAINT fk_history_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_snapshot (
      snapshot_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      snapshot_version VARCHAR(64) NOT NULL,
      status VARCHAR(32) NOT NULL,
      general_kg_version_json JSON NOT NULL,
      pipeline_version VARCHAR(128) NOT NULL,
      model_version VARCHAR(128) NULL,
      query_and_params_json JSON NOT NULL,
      frozen_at DATETIME(6) NOT NULL,
      checksum VARCHAR(128) NOT NULL,
      report_artifact_ref TEXT NOT NULL,
      request_id VARCHAR(64) NULL,
      request_version INT NULL,
      request_content_hash CHAR(64) NULL,
      input_artifact_hashes_json JSON NOT NULL,
      manifest_json JSON NOT NULL,
      UNIQUE KEY uq_experiment_snapshot_version (experiment_id, snapshot_version),
      CONSTRAINT fk_snapshot_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE RESTRICT,
      CONSTRAINT fk_snapshot_request FOREIGN KEY (request_id)
        REFERENCES experiment_request(request_id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_report (
      report_id VARCHAR(64) PRIMARY KEY,
      experiment_id VARCHAR(64) NOT NULL,
      snapshot_id VARCHAR(64) NOT NULL,
      snapshot_version VARCHAR(64) NOT NULL,
      report_format VARCHAR(32) NOT NULL,
      checksum VARCHAR(128) NOT NULL,
      content LONGTEXT NOT NULL,
      sections_json JSON NOT NULL,
      generated_at DATETIME(6) NOT NULL,
      meta_json JSON NOT NULL,
      UNIQUE KEY uq_experiment_report_version (experiment_id, snapshot_version),
      INDEX idx_report_snapshot (snapshot_id),
      CONSTRAINT fk_report_experiment FOREIGN KEY (experiment_id)
        REFERENCES experiment_context(experiment_id) ON DELETE CASCADE,
      CONSTRAINT fk_report_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES experiment_snapshot(snapshot_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


__all__ = ["MYSQL_EXPERIMENT_SCHEMA"]
