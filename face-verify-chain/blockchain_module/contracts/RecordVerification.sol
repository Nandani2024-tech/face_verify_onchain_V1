// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RecordVerification
/// @notice Stores a tamper-evident, timestamped fingerprint (hash) of a
///         discovered piece of content (e.g. a matched social media post),
///         so it can later be re-verified against the on-chain record.
contract RecordVerification {
    /// @dev Record binds a biometric face fingerprint (faceHash) to a specific
    /// verified web post (metadataURI + implicit content hash key), creating
    /// an end-to-end tamper-evident chain: Face -> Search Result -> Blockchain.
    struct Record {
        address submitter;
        uint256 timestamp;
        string metadataURI; // e.g. the matched post's URL, or an IPFS URI
        bytes32 faceHash;   // SHA-256 fingerprint of the face encoding from Step 1
        bool exists;
    }

    // contentHash (keccak256 of the post/image/metadata) => Record
    mapping(bytes32 => Record) private records;

    event RecordStored(
        bytes32 indexed contentHash,
        address indexed submitter,
        uint256 timestamp,
        string metadataURI,
        bytes32 faceHash
    );

    /// @notice Store a new fingerprint on-chain. Reverts if this exact
    ///         hash has already been recorded (prevents silent overwrite).
    function storeRecord(bytes32 contentHash, string calldata metadataURI, bytes32 faceHash) external {
        require(!records[contentHash].exists, "Record already exists");

        records[contentHash] = Record({
            submitter: msg.sender,
            timestamp: block.timestamp,
            metadataURI: metadataURI,
            faceHash: faceHash,
            exists: true
        });

        emit RecordStored(contentHash, msg.sender, block.timestamp, metadataURI, faceHash);
    }

    /// @notice Re-verify a fingerprint against the on-chain record.
    /// @return exists whether a record for this hash exists
    /// @return submitter the address that stored it
    /// @return timestamp when it was stored (unix time)
    /// @return metadataURI the metadata/URL stored alongside it
    /// @return faceHash the 32-byte face fingerprint bound to this post
    function verifyRecord(bytes32 contentHash)
        external
        view
        returns (
            bool exists,
            address submitter,
            uint256 timestamp,
            string memory metadataURI,
            bytes32 faceHash
        )
    {
        Record memory r = records[contentHash];
        return (r.exists, r.submitter, r.timestamp, r.metadataURI, r.faceHash);
    }
}
