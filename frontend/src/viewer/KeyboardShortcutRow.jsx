import React from 'react';

/**
 * KeyboardShortcutRow
 *
 * Renders one table row for a keyboard shortcut. Shows the key sequence in a
 * row header cell and the action description in an adjacent cell.
 *
 * Rendering:
 * - Keys are comma separated with a space
 * - Keys are placed in a <th>, description in a <td>
 *
 * Accessibility:
 * - <kbd> provides semantic markup for key names
 * - Consumers should ensure the surrounding table has proper headers or caption
 *
 * @param {Array<{text: string, wrap: boolean}>} keys - Ordered keys to display.
 *   When wrap is true the key is wrapped in <kbd>, otherwise rendered as plain
 *   text.
 * @param {string} description - Human readable description of the shortcut
 *   action.
 * @returns {JSX.Element}
 */
export default function KeyboardShortcutRow({keys, description}) {
    return (
        <tr>
            <th>
                {keys.map((key, i) => (
                    <React.Fragment key={i}>
                        {key.wrap ? <kbd>{key.text}</kbd> : key.text}
                        {i < keys.length - 1 && ', '}
                    </React.Fragment>
                ))}
            </th>
            <td>{description}</td>
        </tr>
    );
}
