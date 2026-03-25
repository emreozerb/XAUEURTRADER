import React from 'react';

export default function EmergencyButton({ onClick }) {
  return (
    <button className="emergency-btn" onClick={onClick}>
      CLOSE ALL
    </button>
  );
}
