// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RecordVerification
/// @notice Stores a tamper-evident, timestamped fingerprint (hash) of a
///         discovered piece of content (e.g. a matched social media post),
///         so it can later be re-verified against the on-chain record.
contract RecordVerification {
    struct Record {
        address submitter;
        uint256 timestamp;
        string metadataURI; // e.g. the matched post's URL, or an IPFS URI
        bool exists;
    }

    // contentHash (keccak256 of the post/image/metadata) => Record
    mapping(bytes32 => Record) private records;

    event RecordStored(
        bytes32 indexed contentHash,
        address indexed submitter,
        uint256 timestamp,
        string metadataURI
    );

    /// @notice Store a new fingerprint on-chain. Reverts if this exact
    ///         hash has already been recorded (prevents silent overwrite).
    function storeRecord(bytes32 contentHash, string calldata metadataURI) external {
        require(!records[contentHash].exists, "Record already exists");

        records[contentHash] = Record({
            submitter: msg.sender,
            timestamp: block.timestamp,
            metadataURI: metadataURI,
            exists: true
        });

        emit RecordStored(contentHash, msg.sender, block.timestamp, metadataURI);
    }

    /// @notice Re-verify a fingerprint against the on-chain record.
    /// @return exists whether a record for this hash exists
    /// @return submitter the address that stored it
    /// @return timestamp when it was stored (unix time)
    /// @return metadataURI the metadata/URL stored alongside it
    function verifyRecord(bytes32 contentHash)
        external
        view
        returns (bool exists, address submitter, uint256 timestamp, string memory metadataURI)
    {
        Record memory r = records[contentHash];
        return (r.exists, r.submitter, r.timestamp, r.metadataURI);
    }
}
