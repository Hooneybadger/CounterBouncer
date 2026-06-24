#pragma once

#include "./Base.hpp"

class Node
{
public:
    bool _accessible; // Indicates if the node is accessible from the root
    NodeId _position; // Position in the graph for routing. In IP model, loading cars move along position-ascending routes, and unloading cars move along position-descending routes.
    NodeId _pred;
    Distance _dist; // Distance from the root node (distance can be defined in various ways)
    vector<NodeId> _neighborVec; // Neighbors of this node
    Node() : _accessible(true), _position(INF), _pred(INF), _dist(INF), _neighborVec() {}
};