"""Neighbor-graph algebraic connectivity (λ₂) — CLAUDE.md §5: "predicts the
packet-loss threshold at which the swarm fragments."

Each agent reconstructs this graph from gossip, not from a global state read
(CLAUDE.md invariant #2): the "hears" field added to every state broadcast
(see swarm/agent.py) carries the sender's own current set of heard peers, so
any agent can locally assemble a picture of who-hears-whom across the whole
swarm. Under today's perfect comms this agrees with the "true" graph; once
comms degrade (week 5) a partitioned agent's reconstruction will honestly go
stale for the far side of the partition — that staleness is part of the
resilience story, not a bug to paper over.
"""
import numpy as np


def algebraic_connectivity(heard_by, agent_ids):
    """heard_by: {agent_id: set(peer_ids that agent currently hears)}.
    agent_ids: the full fixed set of agent ids in the swarm (config.AGENT_IDS)
    — every id gets a node even if currently silent, so a killed/isolated
    agent shows up as a zero-degree node rather than vanishing from the graph.

    An edge (i, j) exists only if the link is mutual: i hears j AND j hears i.

    Returns lambda_2, the second-smallest eigenvalue of the graph Laplacian
    (Fiedler 1973). 0.0 for a disconnected graph, by definition.
    """
    ids = sorted(agent_ids)
    n = len(ids)
    if n < 2:
        return 0.0
    index = {aid: i for i, aid in enumerate(ids)}

    adjacency = np.zeros((n, n))
    for i_id, heard in heard_by.items():
        if i_id not in index:
            continue
        for j_id in heard:
            if j_id not in index:
                continue
            if i_id in heard_by.get(j_id, ()):  # mutual link only
                adjacency[index[i_id], index[j_id]] = 1
                adjacency[index[j_id], index[i_id]] = 1

    degree = np.diag(adjacency.sum(axis=1))
    laplacian = degree - adjacency
    eigenvalues = np.linalg.eigvalsh(laplacian)  # ascending, laplacian is symmetric
    return float(eigenvalues[1])
