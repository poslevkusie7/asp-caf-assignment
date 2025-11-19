#ifndef TREE_H
#define TREE_H

#include <unordered_map>
#include <map>
#include <string>
#include <utility>

#include "tree_record.h"

class Tree {
public:
    const std::map<std::string, TreeRecord> records;

    explicit Tree(const std::unordered_map<std::string, TreeRecord>& input): records(input.begin(), input.end()) {}

    std::map<std::string, TreeRecord>::const_iterator record(const std::string& key) const {
        return records.find(key);
    }
};

#endif // TREE_H

